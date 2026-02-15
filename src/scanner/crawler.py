import json
from playwright.sync_api import sync_playwright, Page, Request
from urllib.parse import urlparse, urljoin

from src.scanner.deduplicator import Deduplicator
from src.scanner.auth_handler import AuthHandler
from src.core.logger import setup_logger

from src.utils.browser_helper import dismiss_obstacles, trigger_hidden_elements, safe_wait
from src.utils.url_helper import is_internal_url, is_static_resource, normalize_url


class Crawler:
    def __init__(self, cred: dict, logger=None):
        self.deduplicator = Deduplicator()
        self.logger = logger or setup_logger("Crawler")
        self.collected_targets = []
        self.visited_urls = set()
        self.auth_handler = AuthHandler()
        self.is_authenticated = False
        self.credential = cred
        self.blacklisted_domains = ["facebook.com", "youtube.com", "google.com", "linkedin.com", "github.com"]

    # --- Core Crawl Method ---

    def crawl(self, start_url: str, max_depth: int = 2):
        self.logger.info(f"[Crawler] Starting Modern Crawl on: {start_url}")
        parsed_start = urlparse(start_url)
        base_domain = parsed_start.netloc 
        base_scheme = parsed_start.scheme
        queue = [(start_url, 0)]
        
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=False)
            context = browser.new_context(ignore_https_errors=True)
            page = context.new_page()

            page.on("dialog", lambda d: d.accept())
            page.on("request", lambda req: self._intercept_network(req, base_domain))

            while queue:
                current_url, current_depth = queue.pop(0) 
                clean_url = normalize_url(current_url)
                
                if clean_url in self.visited_urls or self._is_static_resource(current_url):
                    continue
                if current_depth > max_depth: continue

                self.visited_urls.add(clean_url)

                try:
                    # [SESSION] แปะ Cookies/Storage ถ้าเคย Login แล้ว
                    if self.is_authenticated:
                        self.auth_handler.apply_session(context)

                    response = page.goto(current_url, wait_until="networkidle", timeout=15000)

                    if urlparse(page.url).netloc != base_domain:
                        self.logger.warning(f"[-] Out of scope: {page.url}")
                        continue

                    dismiss_obstacles(page)
                    trigger_hidden_elements(page)
                    safe_wait(page, 500)

                    # 2. SPA Heuristic Path Discovery
                    important_keywords = {
                        "Administration": "/#/administration", "Score Board": "/#/score-board",
                        "Login": "/#/login", "Basket": "/#/basket"
                    }
                    for kw, path in important_keywords.items():
                        try:
                            if page.get_by_text(kw).first.is_visible(timeout=300):
                                h_url = f"{base_scheme}://{base_domain}{path}"
                                if h_url.split('?')[0].rstrip('/') not in self.visited_urls:
                                    queue.append((h_url, current_depth + 1))
                        except: continue

                    # 3. Auth Logic (เชื่อมกับ AuthHandler persistence)
                    if not self.is_authenticated and self.credential:
                        if self.auth_handler.find_and_login(page, self.credential):
                            self.is_authenticated = True
                            # เมื่อ Login สำเร็จ ให้เริ่มสำรวจหน้าใหม่ด้วย Session ใหม่
                            queue.insert(0, (page.url, current_depth))
                            continue

                    # 4. Data Extraction
                    if response and response.status < 400:
                        found_params = self._process_page(page, current_url)
                        if found_params:
                            self._save_target(current_url, found_params, "GET")

                        if current_depth < max_depth:
                            for link in self._discover_links(page, current_url, base_domain):
                                queue.append((link, current_depth + 1))

                except Exception as e:
                    self.logger.debug(f"[-] Skip {current_url}: {e}")

            browser.close()
        return self.collected_targets

    def _intercept_network(self, request: Request, base_domain: str):
        # กรองเอาเฉพาะ Fetch/XHR และข้ามพวก socket.io เพื่อลดขยะใน Log
        if request.resource_type in ["fetch", "xhr"] and "socket.io" not in request.url:
            if urlparse(request.url).netloc == base_domain:
                params = {}
                try:
                    if request.post_data:
                        data = json.loads(request.post_data)
                        if isinstance(data, dict):
                            params = {k: "val" for k in data.keys()}
                except: pass
                self._save_target(request.url, params, request.method, "json")

    def _process_page(self, page: Page, url: str) -> dict:
        params = {}
        # URL Params
        if "?" in url:
            for pair in urlparse(url).query.split("&"):
                if "=" in pair:
                    k, v = pair.split("=", 1)
                    params[k] = v
        
        # Smart Element Discovery
        selectors = "input, textarea, select, [role='textbox'], .mdc-text-field__input"
        for i, el in enumerate(page.query_selector_all(selectors)):
            try:
                p_name = (el.get_attribute("name") or el.get_attribute("id") or 
                          el.get_attribute("placeholder") or el.get_attribute("aria-label") or f"p_{i}")
                
                if "mat-input-1" in p_name: params["q"] = "fuzz"
                else: params[p_name] = "test"
            except: continue
        return params

    def _save_target(self, url: str, params: dict, method: str = "GET", content_type: str = "form"):
        # ตัด fragment (#) ออกตอนทำ Signature เพื่อป้องกันการเก็บซ้ำในบาง API
        base_url = url.split("?")[0].split("#")[0]
        method = method.upper() 
        sig = f"{method}|{base_url}|{sorted(params.keys())}"

        if not self.deduplicator.is_seen(sig):
            self.deduplicator.add(sig)
            self.collected_targets.append({
                "url": base_url, "method": method, 
                "content_type": content_type, "params": params
            })
            self.logger.info(f"     [+] Discovered: {method} {base_url} ({len(params)} params)")

    def _discover_links(self, page: Page, current_url: str, allowed_domain: str) -> set:
        links_found = set()
        for a in page.query_selector_all("a[href]"):
            try:
                href = a.get_attribute("href")
                if not href or href.strip().startswith(("javascript:", "mailto:", "tel:", "#")): continue
                full_url = urljoin(current_url, href)
                if urlparse(full_url).netloc == allowed_domain and not any(d in full_url for d in self.blacklisted_domains):
                    links_found.add(full_url)
            except: continue

        for btn in page.query_selector_all("[routerlink], [href]:not(a)"):
            try:
                path = btn.get_attribute("routerlink") or btn.get_attribute("href")
                full_url = urljoin(current_url, path)
                if urlparse(full_url).netloc == allowed_domain:
                    links_found.add(full_url)
            except: continue
        return links_found