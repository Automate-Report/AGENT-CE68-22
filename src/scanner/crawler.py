import asyncio
import json
import re
from playwright.async_api import async_playwright, Request, Response
from urllib.parse import urlparse, urljoin,  parse_qs, unquote
from contextlib import asynccontextmanager

from src.scanner.deduplicator import Deduplicator
from src.scanner.interaction import InteractionEngine
from src.scanner.link_extractor import LinkExtractor
from src.scanner.param_extractor import ParameterExtractor
from src.scanner.auth_handler import AuthHandler

from src.core.logger import setup_logger

from src.utils.browser_helper import dismiss_obstacles, trigger_hidden_elements, safe_wait
from src.utils.url_helper import is_static_resource, normalize_url


class Crawler:
    def __init__(self, cred: dict = None, logger=None):
        self.logger = logger or setup_logger("Crawler")
        self.deduplicator = Deduplicator()
        self.interactor = InteractionEngine(self.logger)
        self.param_extractor = ParameterExtractor(self.logger)
        self.link_extractor = LinkExtractor("", []) 
        self.auth_handler = AuthHandler(self.logger)
        self.collected_targets = []
        self.visited_urls = set()
        self.credential = cred
        self.is_authenticated = False
        self.semaphore = asyncio.Semaphore(2)

    # --- Core Crawl Method ---
    @asynccontextmanager
    async def get_browser_context(self):
        """Helper สำหรับให้ Orchestrator ยืม Browser ไปใช้ Login"""
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(ignore_https_errors=True)

            if hasattr(self, 'external_cookies') and self.external_cookies:
                await context.add_cookies(self.external_cookies)

            yield context
            await browser.close()

    async def crawl(self, start_url: str, max_depth: int = 2):
        # Reset state for each crawl call so Phase 3 (authenticated) doesn't
        # skip pages that were already visited in Phase 1 (unauthenticated).
        self.visited_urls    = set()
        self.collected_targets = []

        # Strip URL fragment (e.g. #/search) — Playwright navigates to base URL
        # and fragments cause dedup misses between Phase 1 and Phase 3 seeds.
        clean_start = start_url.split('#')[0].rstrip('/')

        self.logger.info(f"🚀 Starting Async Crawl: {start_url}")
        queue = asyncio.Queue()
        await queue.put((clean_start, 0))
        base_domain = urlparse(clean_start).netloc

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                ignore_https_errors=True,
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )

            if hasattr(self, 'external_cookies') and self.external_cookies:
                # ตรวจสอบว่าคุกกี้มี Domain หรือยัง ถ้าไม่มีให้แปะ Domain เข้าไป
                for cookie in self.external_cookies:
                    if 'domain' not in cookie:
                        cookie['domain'] = base_domain
                
                await context.add_cookies(self.external_cookies)
                self.logger.info(f"[Crawler] 🍪 Context initialized with {len(self.external_cookies)} cookies")

            while not queue.empty():
                current_url, depth = await queue.get()

                if current_url in self.visited_urls or depth > max_depth:
                    queue.task_done()
                    continue

                try:
                    async with self.semaphore:
                        await self._process_url(current_url, depth, context, queue, base_domain, max_depth)
                except Exception as e:
                    self.logger.error(f"Critical error processing {current_url}: {e}")
                finally:
                    queue.task_done()
                    # ใส่ delay เล็กน้อยเพื่อไม่ให้เครื่องค้าง
                    await asyncio.sleep(0.5)

            await browser.close()
        return self.collected_targets
    
    def set_external_cookies(self, cookies: list):
        """รับคุกกี้จากภายนอก (เช่น จาก AuthHandler)"""
        try:
            if not cookies:
                return
            self.external_cookies = cookies
            self.logger.info(f"[Crawler] 🍪 External cookies set. Total: {len(self.external_cookies)}")
        except Exception as e:
            self.logger.error(f"[Crawler] ❌ Error setting external cookies: {e}")

    async def _process_url(self, url, depth, context, queue, base_domain, max_depth):
        """Visit a URL, capture real API calls during interaction, extract params and links."""
        clean_url = url.split('#')[0].rstrip('/')
        if clean_url in self.visited_urls and depth > 0:
            return

        page = await context.new_page()

        # ── Real-time API call collector ──────────────────────────────────────
        # Collect fetch/XHR requests that fire DURING behavioral interaction.
        # Runs sync (Playwright callback restriction) — results processed after.
        api_calls_seen = []

        def on_request(req):
            req_url  = req.url
            req_type = req.resource_type
            method   = req.method.upper()

            # Skip static assets, HMR, websockets
            if any(x in req_url for x in [".js", ".css", ".png", ".jpg", ".woff",
                                           "socket.io", "_next/static", "_next/webpack",
                                           "__webpack", ".hot-update", "maps.googleapis"]):
                return

            # Skip Next.js RSC / internal navigation requests (these are framework-internal)
            if any(k in req_url for k in ["_rsc=", "_next/data", "__nextjs"]):
                return

            # Only capture data requests
            if req_type not in ("fetch", "xhr"):
                return

            api_calls_seen.append({
                "url":       req_url,
                "method":    method,
                "post_data": req.post_data,
            })
            self.logger.debug(f"  [API] Captured: {method} {req_url}")

        page.on("request", on_request)
        # ─────────────────────────────────────────────────────────────────────

        try:
            self.logger.info(f"  [..] Processing: {clean_url} (Depth: {depth})")
            await page.goto(clean_url, wait_until="networkidle", timeout=15000)

            # Generic session expiry check
            is_on_login_page   = any(kw in page.url.lower() for kw in ["login", "signin", "auth"])
            was_targeting_login = any(kw in clean_url.lower() for kw in ["login", "signin", "auth"])
            if is_on_login_page and not was_targeting_login:
                self.logger.warning(f"⚠️ [Crawler] Session expired / redirected to login at {clean_url}")
                return

            # Wait for nav elements
            for selector in ['#menu', '.sidebar', 'nav']:
                try:
                    await page.wait_for_selector(selector, timeout=1000)
                    break
                except: continue

            # 2. Behavioral interaction — fills inputs, presses Enter, clicks.
            #    Resulting fetch/XHR calls are captured by on_request above.
            #    Set target origin so scope guard can block external navigation.
            parsed_origin = urlparse(clean_url)
            self.interactor._target_origin = f"{parsed_origin.scheme}://{parsed_origin.netloc}"
            try:
                await asyncio.wait_for(
                    self.interactor.trigger_smart_interaction(page),
                    timeout=20.0   # 5 phases need more time than single-phase did
                )
            except asyncio.TimeoutError:
                self.logger.debug(f"  [!] Interaction timeout at {clean_url}")
            except Exception as e:
                self.logger.debug(f"  [!] Interaction error: {e}")

            # Wait for debounced / lazy requests to settle
            await asyncio.sleep(1.5)

            # 3. Save captured real API calls as scan targets
            for entry in api_calls_seen:
                params = {}
                parsed_qs = parse_qs(urlparse(entry["url"]).query, keep_blank_values=True)
                params.update({k: v[0] for k, v in parsed_qs.items()})

                if entry["post_data"]:
                    try:
                        params.update(json.loads(entry["post_data"]))
                    except:
                        try:
                            body_qs = parse_qs(entry["post_data"], keep_blank_values=True)
                            params.update({k: v[0] for k, v in body_qs.items()})
                        except: pass

                c_type = "json" if entry["post_data"] and entry["post_data"].strip().startswith("{") else "form"

                # Tag calls going to a different host:port as backend API —
                # DOM scanning is meaningless on pure JSON REST endpoints.
                api_parsed  = urlparse(entry["url"])
                is_backend  = api_parsed.netloc != base_domain

                target_entry = {
                    "url":         entry["url"],
                    "method":      entry["method"],
                    "params":      params,
                    "content_type": c_type,
                }
                if is_backend:
                    target_entry["backend_api"] = True  # skip DOM scan in scan_engine

                self._save_target_entry(target_entry)

            # 4. Extract named form inputs from DOM
            params = await self.param_extractor.extract_from_dom(page)
            if params:
                self._save_target(clean_url, params, "GET", "form")
            else:
                self._save_target(clean_url, {}, "GET", "form")

            # 5. Extract links for further crawling
            if depth < max_depth:
                links = await self.link_extractor.extract(page, clean_url)
                for link in links:
                    parsed_link    = urlparse(link)
                    normalized_link = f"{parsed_link.scheme}://{parsed_link.netloc}{parsed_link.path}".rstrip('/')
                    if parsed_link.netloc == base_domain and normalized_link not in self.visited_urls:
                        self.visited_urls.add(normalized_link)
                        await queue.put((link, depth + 1))

        except Exception as e:
            self.logger.error(f"[!] Failed to process {clean_url}: {str(e)[:80]}")
        finally:
            await page.close()


    def _intercept_network(self, request: Request, base_domain: str):
        url = request.url
        # 1. ข้ามสิ่งที่ไม่สนใจ (Static Files)
        if any(x in url for x in ["socket.io", ".jpg", ".png", ".css", ".woff2", "maps.googleapis.com"]):
            return

        # 2. เช็คว่าเป็น Internal Domain หรือ API Path หรือไม่
        is_internal = base_domain in url
        is_api = "/api/" in url or "/rest/" in url

        if is_internal or is_api:
            if request.resource_type in ["fetch", "xhr"]:
                method = request.method.upper()
                params = {}
                
                # --- จุดที่ต้องแก้ไข: ดัก Query Params แบบ Generic ---
                parsed_url = urlparse(url)
                # เพิ่ม keep_blank_values=True เพื่อดักจับพารามิเตอร์ทุกตัวแม้ไม่มีค่า (เช่น ?q=)
                qs = parse_qs(parsed_url.query, keep_blank_values=True)
                
                # อัปเดตพารามิเตอร์เข้า dict (เอาเฉพาะค่าแรกที่พบ)
                params.update({k: v[0] for k, v in qs.items()})
                # ------------------------------------------------

                # ดัก POST Body (JSON)
                if request.post_data:
                    try:
                        params.update(json.loads(request.post_data))
                    except: 
                        pass

                # Strip framework-internal params before saving
                real_params = {k: v for k, v in params.items()
                               if not any(k.lower().startswith(p)
                                          for p in ("_rsc", "_next", "__next", "utm_", "fbclid", "gclid"))}
                if real_params:  # Only save if there are real (user-controlled) params
                    self._save_target(url, real_params, method, "json")
                # If all params were internal, skip — the page will be saved as a
                # static DOM-only target when the crawler visits it with page.goto()

    async def _intercept_response(self, response: Response):
        if self.deduplicator.is_pii_reported(response.url): return
        
        try:
            ct = response.headers.get("content-type", "").lower()
            if "json" in ct or "text" in ct:
                body = await response.text()
                if re.search(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', body):
                    self.logger.warning(f" [!] PII Leak (Email) detected: {response.url}")
        except: pass

    async def _extract_params(self, page):
        params = {}
        elements = await page.locator("input:visible, textarea:visible, select:visible").all()
        for i, el in enumerate(elements):
            try:
                name = await el.get_attribute("name") or await el.get_attribute("placeholder") or f"input_{i}"
                params[name] = ""
            except: continue
        return params

    async def _extract_links(self, page, current_url, base_domain):
        links_found = set()
        hrefs = await page.evaluate("""() => Array.from(document.querySelectorAll('a[href]')).map(a => a.href)""")
        for href in hrefs:
            full_url = urljoin(current_url, href)
            if urlparse(full_url).netloc == base_domain:
                links_found.add(full_url.split('#')[0])
        return links_found

    # Framework-internal param prefixes — never scannable via HTTP fuzzing
    _INTERNAL_PREFIXES = ("_rsc", "_next", "__next", "__react", "_vercel", "utm_", "fbclid", "gclid")

    def _is_internal_param(self, key: str) -> bool:
        lk = key.lower()
        return any(lk.startswith(p) for p in self._INTERNAL_PREFIXES)

    def _save_target(self, url, params, method, c_type):
        parsed   = urlparse(url)
        clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

        # 1. Merge query-string params into the dict
        query_params = parse_qs(parsed.query)
        for k, v in query_params.items():
            if k not in params:
                params[k] = v[0]

        # 2. Strip all framework-internal params
        real_params = {k: v for k, v in params.items() if not self._is_internal_param(k)}

        # 3. Path-parameter (IDOR) detection
        for i, part in enumerate(parsed.path.split('/')):
            if part.isdigit():
                real_params[f"path_id_{i}"] = part

        # 4a. Has real (user-controlled) params → save as a normal scan target
        if real_params:
            target_url = f"{clean_url}?{'&'.join(f'{k}={v}' for k, v in real_params.items())}"
            if not self.deduplicator.is_seen(method, clean_url, real_params):
                self.collected_targets.append({
                    "url":          target_url,
                    "method":       method,
                    "params":       real_params,
                    "content_type": c_type,
                })
                self.logger.info(f"    [+] Target Saved: {method} {target_url}")

        # 4b. No real params → save base URL for DOM-only XSS scanning
        #     (e.g. /register reached via RSC — still worth checking DOM sinks)
        else:
            dom_key = ("DOM", clean_url, "{}")
            if not self.deduplicator.is_seen("GET", clean_url, {}):
                self.collected_targets.append({
                    "url":          clean_url,
                    "method":       "GET",
                    "params":       {},
                    "content_type": "form",
                    "dom_only":     True,   # flag: skip reflected scan, do DOM only
                })
                self.logger.info(f"    [+] DOM Target Saved: GET {clean_url}")

    def _save_target_entry(self, entry: dict):
        """
        Save a fully-formed target dict (with any custom flags like backend_api).
        Strips internal params and deduplicates before appending.
        """
        url    = entry.get("url", "")
        method = entry.get("method", "GET")
        params = dict(entry.get("params", {}))
        c_type = entry.get("content_type", "form")
        extras = {k: v for k, v in entry.items()
                  if k not in ("url", "method", "params", "content_type")}

        parsed    = urlparse(url)
        clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

        # Merge query-string params
        for k, v in parse_qs(parsed.query).items():
            if k not in params:
                params[k] = v[0]

        # Strip internal params
        real_params = {k: v for k, v in params.items() if not self._is_internal_param(k)}

        if real_params:
            target_url = f"{clean_url}?{'&'.join(f'{k}={v}' for k, v in real_params.items())}"
            if not self.deduplicator.is_seen(method, clean_url, real_params):
                target = {"url": target_url, "method": method,
                          "params": real_params, "content_type": c_type}
                target.update(extras)
                self.collected_targets.append(target)
                tag = " [backend API]" if extras.get("backend_api") else ""
                self.logger.info(f"    [+] Target Saved{tag}: {method} {target_url}")
        else:
            if not self.deduplicator.is_seen("GET", clean_url, {}):
                target = {"url": clean_url, "method": "GET", "params": {},
                          "content_type": "form", "dom_only": True}
                target.update(extras)
                self.collected_targets.append(target)
                self.logger.info(f"    [+] DOM Target Saved: GET {clean_url}")

