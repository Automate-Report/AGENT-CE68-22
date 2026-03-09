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
            browser = await p.chromium.launch(headless=False)
            context = await browser.new_context(ignore_https_errors=True)
            yield context
            await browser.close()

    async def crawl(self, start_url: str, max_depth: int = 2):
        self.logger.info(f"🚀 Starting Async Crawl: {start_url}")
        queue = asyncio.Queue()
        await queue.put((start_url, 0))
        base_domain = urlparse(start_url).netloc

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False) # สังเกตการทำงาน
            context = await browser.new_context(ignore_https_errors=True)

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

    async def _process_url(self, url, depth, context, queue, base_domain, max_depth=2):
        self.link_extractor.base_domain = base_domain
        self.link_extractor.blacklist = [base_domain, "facebook.com", "twitter.com", "youtube.com", "github.com"] # ป้องกันการออกนอกโดเมน

        page = await context.new_page()
        page.on("request", lambda req: self._intercept_network(req, base_domain))
        
        try:
            self.logger.info(f"[*] Visiting: {url}")
            # ใช้ networkidle เพื่อให้แน่ใจว่า SPA โหลด Component เสร็จ
            await page.goto(url, wait_until="networkidle", timeout=30000)

            # --- ส่วนที่เพิ่ม: กำจัด Welcome Banner ของ Juice Shop ---
            try:
                # รอให้ปุ่มปิดโผล่มา (ใช้ Selector ที่ครอบคลุม)
                welcome_btn = page.locator("button[aria-label='Close Welcome Banner'], button:has-text('Dismiss')")
                if await welcome_btn.is_visible():
                    await welcome_btn.click()
                
                # ปิด Cookie Consent ด้วย
                cookie_btn = page.locator(".cc-dismiss, button:has-text('Got it!')")
                if await cookie_btn.is_visible():
                    await cookie_btn.click()
            except: pass 

            # 1. Extract Params & Save (ทำก่อน Interaction)
            params = await self.param_extractor.extract_from_dom(page)
            self._save_target(url, params, "GET", "form")

            # 2. Trigger Interaction (คลิกปุ่มต่างๆ เพื่อหา API)
            await self.interactor.trigger_smart_interaction(page)

            # 3. Extract Links สำหรับหน้าถัดไป
            if depth < max_depth:
                links = await self.link_extractor.extract(page, url)
                for link in links:
                    # Normalize ลิงก์เบื้องต้น (เช่น ตัด / ท้ายสุดออก)
                    normalized_link = link.rstrip('/')
                    if normalized_link not in self.visited_urls:
                        # สำคัญ: ต้อง add ทันทีเพื่อไม่ให้ Queue รับงานซ้ำ
                        self.visited_urls.add(normalized_link) 
                        await queue.put((normalized_link, depth + 1))

        except Exception as e:
            # เก็บ Log error ให้ละเอียดขึ้นเล็กน้อยเพื่อการ Debug
            self.logger.error(f"[!] Failed to process {url}: {str(e)[:100]}")
        finally:
            # สำคัญมาก: ต้องปิดหน้าเสมอเพื่อคืน Memory
            await page.close()

    def _intercept_network(self, request: Request, base_domain: str):
        if "socket.io" in request.url:
            return
        if urlparse(request.url).netloc != base_domain: return
        if any(x in request.url for x in [".jpg", ".png", ".css", ".woff2"]): return

        if request.resource_type in ["fetch", "xhr"]:
            method = request.method.upper()
            params = {}
            
            # ดัก Query Params
            qs = parse_qs(urlparse(request.url).query)
            params.update({k: v[0] for k, v in qs.items()})

            # ดัก POST Body
            if request.post_data:
                try:
                    params.update(json.loads(request.post_data))
                except: pass

            if params or method != "GET":
                self._save_target(request.url, params, method, "json")

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

    def _save_target(self, url, params, method, c_type):
        # ไม่ต้อง split('?')[0] ตรงนี้ เพราะ Deduplicator ของเรารองรับการจัดการ URL เองแล้ว
        if not self.deduplicator.is_seen(method, url, params):
            target = {
                "url": url.split('?')[0], # เก็บลงรายงานแบบสะอาด
                "method": method,
                "params": params,
                "content_type": c_type
            }
            self.collected_targets.append(target)
            self.logger.info(f"    [+] Target Discovered: {method} {url}")


