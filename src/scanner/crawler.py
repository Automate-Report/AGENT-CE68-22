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

            if hasattr(self, 'external_cookies') and self.external_cookies:
                await context.add_cookies(self.external_cookies)

            yield context
            await browser.close()

    async def crawl(self, start_url: str, max_depth: int = 2):
        self.logger.info(f"🚀 Starting Async Crawl: {start_url}")
        queue = asyncio.Queue()
        await queue.put((start_url, 0))
        base_domain = urlparse(start_url).netloc

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False) # สังเกตการทำงาน
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
        """
        รับคุกกี้จากภายนอก (เช่น จาก AuthHandler) 
        มาเก็บไว้ในตัวแปรของ Crawler เพื่อใช้ในทุก Browser Context ต่อจากนี้
        """
        try:
            if not cookies:
                return

            security_keywords = ['security', 'level', 'difficulty', 'vulnerability']
    
            for cookie in cookies:
                if any(key in cookie['name'].lower() for key in security_keywords):
                    # ถ้าเจอ ให้ลองปรับค่าเป็น 'low' หรือ '0' (แบบ Generic)
                    if cookie['value'].lower() in ['high', 'impossible', 'medium', '2', '1']:
                        self.logger.info(f"[Crawler] 🛠 Overriding security cookie '{cookie['name']}' to 'low'")
                        cookie['value'] = 'low'
            
            self.external_cookies = cookies
            
            # 2. พิเศษสำหรับ DVWA หรือเว็บที่มี Security Level
            # ตรวจสอบว่าในคุกกี้มี 'security' หรือยัง ถ้าไม่มีให้ฉีดเข้าไปเป็น 'low' (Generic Logic)
            has_security_cookie = any(c['name'] == 'security' for c in cookies)
            if not has_security_cookie:
                self.external_cookies.append({
                    'name': 'security',
                    'value': 'low',
                    'domain': 'localhost', # หรือดึงจาก urlparse(self.base_url).hostname
                    'path': '/'
                })

            self.logger.info(f"[Crawler] 🍪 External cookies set. Total: {len(self.external_cookies)}")
        except Exception as e:
            self.logger.error(f"[Crawler] ❌ Error setting external cookies: {e}")

    async def _process_url(self, url, depth, context, queue, base_domain, max_depth):
        # 1. Normalize URL ก่อนเริ่มงาน (ตัด fragment # ออก)
        clean_url = url.split('#')[0].rstrip('/')
        
        # ป้องกันการประมวลผลซ้ำ (Double Check)
        if clean_url in self.visited_urls and depth > 0:
            return

        page = await context.new_page()
        page.on("request", lambda req: self._intercept_network(req, base_domain))
        
        try:
            self.logger.info(f"  [..] Processing: {clean_url} (Depth: {depth})")
            response = await page.goto(clean_url, wait_until="networkidle", timeout=15000)
            
            if "login.php" in page.url and "login.php" not in clean_url:
                self.logger.warning(f"⚠️ [Crawler] Session expired at {clean_url}")
                return

            # รอเมนูโผล่ (ใช้เวลาสั้นลง)
            for selector in ['#menu', '.sidebar', 'nav']:
                try:
                    await page.wait_for_selector(selector, timeout=1000)
                    break 
                except: continue

            # 2. Smart Interaction (ใส่ Timeout เพื่อกันลูป/ค้าง)
            try:
                # ถ้า interaction นานเกิน 5 วินาที ให้ข้ามไปเก็บลิงก์เลย
                await asyncio.wait_for(self.interactor.trigger_smart_interaction(page), timeout=5.0)
            except asyncio.TimeoutError:
                self.logger.debug(f"  [!] Interaction timeout at {clean_url}")
            except Exception as e:
                self.logger.debug(f"  [!] Interaction error: {e}")

            # 3. Extract Parameters
            params = await self.param_extractor.extract_from_dom(page)
            if params:
                self._save_target(clean_url, params, "GET", "form")

            # 4. Extract Links (กวาดหน้าอื่นๆ)
            if depth < max_depth:
                links = await self.link_extractor.extract(page, clean_url)
                for link in links:
                    # 🚩 หัวใจสำคัญ: ล้าง URL ก่อนเอาใส่ Queue
                    parsed_link = urlparse(link)
                    # ตัด fragment และ query string บางส่วนที่ทำให้เกิด loop ออก
                    normalized_link = f"{parsed_link.scheme}://{parsed_link.netloc}{parsed_link.path}".rstrip('/')
                    
                    if parsed_link.netloc == base_domain and normalized_link not in self.visited_urls:
                        # Mark ว่าจะไปแล้วนะ (ป้องกันตัวอื่นเอาลง queue ซ้ำ)
                        self.visited_urls.add(normalized_link)
                        await queue.put((link, depth + 1))

        except Exception as e:
            self.logger.error(f"[!] Failed to process {clean_url}: {str(e)[:50]}")
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

                # บันทึกเป้าหมายเข้าลิสต์และเซฟลงไฟล์ทันที
                self._save_target(url, params, method, "json")

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
        parsed = urlparse(url)
        clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        
        # 1. ดึงพารามิเตอร์จาก Query String มารวมกับ params ที่มีอยู่
        query_params = parse_qs(parsed.query)
        for k, v in query_params.items():
            if k not in params:
                params[k] = v[0] # เก็บค่าตัวอย่างไว้ดู

        # 2. Logic พิเศษ: ถ้า URL มีเลข (เช่น /products/1/) ให้เดาว่าเป็น Path Parameter (IDOR)
        path_parts = parsed.path.split('/')
        for i, part in enumerate(path_parts):
            if part.isdigit():
                params[f"path_id_{i}"] = part

        if not self.deduplicator.is_seen(method, clean_url, params):
            target = {
                "url": url,
                "method": method,
                "params": params,
                "content_type": c_type

            }
            self.collected_targets.append(target)
            
            # --- เพิ่มตรงนี้: เซฟลงไฟล์ทันทีป้องกันหาย ---
            # with open("raw_targets.json", "w") as f:
            #     json.dump(self.collected_targets, f, indent=2)
                
            self.logger.info(f"    [+] Target Saved: {method} {url}")


