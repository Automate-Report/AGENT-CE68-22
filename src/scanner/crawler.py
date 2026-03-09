import asyncio
import json
import re
from playwright.async_api import async_playwright, Request, Response
from urllib.parse import urlparse, urljoin,  parse_qs, unquote

from src.scanner.deduplicator import Deduplicator
from src.scanner.interaction import InteractionEngine
from src.scanner.link_extractor import LinkExtractor
from src.scanner.param_extractor import ParameterExtractor
from src.scanner.auth_handler import AuthHandler

from src.core.logger import setup_logger

from src.utils.browser_helper import dismiss_obstacles, trigger_hidden_elements, safe_wait
from src.utils.url_helper import is_static_resource, normalize_url


class Crawler:
    def __init__(self, cred: dict, logger=None):
        self.logger = logger or setup_logger("Crawler")
        self.deduplicator = Deduplicator()
        self.interactor = InteractionEngine(self.logger)
        self.param_extractor = ParameterExtractor(self.logger)
        self.auth_handler = AuthHandler(self.logger)
        self.collected_targets = []
        self.visited_urls = set()
        self.credential = cred
        self.is_authenticated = False
        self.semaphore = asyncio.Semaphore(5)

    # --- Core Crawl Method ---

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

                # จำกัดจำนวน concurrency ด้วย semaphore
                async with self.semaphore:
                    await self._process_url(current_url, depth, context, queue, base_domain)
                
                queue.task_done()

            await browser.close()
        return self.collected_targets

    async def _process_url(self, url, depth, context, queue, base_domain):
        # 1. ย้ายการสร้าง LinkExtractor ไปไว้ใน __init__ จะดีกว่า 
        # แต่ถ้าจะสร้างตรงนี้ ควรตรวจสอบสะกดคำผิด (yputube -> youtube)
        link_ext = LinkExtractor(base_domain, ["facebook.com", "google.com", "youtube.com", "linkedin.com", "github.com"])

        self.visited_urls.add(url)
        page = await context.new_page()
        
        # ดักจับ Network และ PII (ใช้ lambda เพื่อส่ง base_domain เข้าไป)
        page.on("request", lambda req: self._intercept_network(req, base_domain))
        page.on("response", lambda res: self._intercept_response(res))

        try:
            self.logger.info(f"[*] Visiting: {url} (Depth: {depth})")
            
            # ปรับ wait_until เป็น domcontentloaded เพื่อความเร็ว 
            # และใช้ networkidle สั้นๆ ใน trigger_smart_interaction แทน
            await page.goto(url, wait_until="domcontentloaded", timeout=25000)
            
            # เพิ่ม safe wait สั้นๆ เผื่อกรณีเว็บเป็น SPA ที่โหลด component ช้า
            await page.wait_for_timeout(1000)

            # 1. Extract Parameters โดยใช้ Module ที่แยกออกมา
            # แทนที่ self._extract_params(page) เดิม
            params = await self.param_extractor.extract_from_dom(page)
            if params:
                self._save_target(url, params, "GET", "form")

            # 2. กระตุ้น API Call (ส่วนนี้จะทำให้เกิด Network traffic ที่ _intercept_network ดักได้)
            await self.interactor.trigger_smart_interaction(page)

            # 3. ค้นหา Link ใหม่ๆ โดยใช้ Module ที่แยกออกมา
            if depth < 2:
                # แทนที่ self._extract_links(page, url, base_domain) เดิม
                links = await link_ext.extract(page, url)
                for link in links:
                    if link not in self.visited_urls:
                        # ใช้ await queue.put เพื่อป้องกันคิวค้างในระบบ async
                        await queue.put((link, depth + 1))

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
        clean_url = url.split('?')[0]
        if not self.deduplicator.is_seen(method, clean_url, params):
            target = {
                "url": clean_url,
                "method": method,
                "params": params,
                "content_type": c_type
            }
            self.collected_targets.append(target)
            self.logger.info(f"    [+] Target Discovered: {method} {clean_url}")