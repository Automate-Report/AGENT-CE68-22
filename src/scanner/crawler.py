import json
from playwright.sync_api import sync_playwright, Page, Request
from urllib.parse import urlparse, urljoin,  parse_qs, unquote

from src.scanner.deduplicator import Deduplicator
from src.scanner.auth_handler import AuthHandler
from src.core.logger import setup_logger

from src.utils.browser_helper import dismiss_obstacles, trigger_hidden_elements, safe_wait
from src.utils.url_helper import is_static_resource, normalize_url


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
        base_domain = urlparse(start_url).netloc
        queue = [(start_url, 0)]
        
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=False) # สังเกตการทำงานได้
            context = browser.new_context(ignore_https_errors=True)
            page = context.new_page()

            while queue:
                current_url, current_depth = queue.pop(0)
                
                # 1. กรองไฟล์ Static และ URL ที่เคยไปแล้ว
                if is_static_resource(current_url) or current_url in self.visited_urls:
                    continue
                if current_depth > max_depth: continue
                
                self.visited_urls.add(current_url)

                try:
                    # 2. เข้าหน้าเว็บ (เพิ่มความทนทานต่อ Timeout)
                    self.logger.debug(f"[*] Visiting: {current_url}")
                    page.goto(current_url, wait_until="domcontentloaded", timeout=25000)
                    
                    # 3. ใช้ Utils เคลียร์หน้าจอและกระตุ้นปุ่มซ่อน
                    dismiss_obstacles(page)
                    trigger_hidden_elements(page)
                    safe_wait(page, 1000) # รอให้ SPA render content

                    # 4. สกัดพารามิเตอร์ (Smart extraction)
                    found_params = self._process_page(page, current_url)
                    if found_params:
                        self._save_target(current_url, found_params, "GET")

                    # 5. ค้นหา Link เพื่อไปต่อ
                    if current_depth < max_depth:
                        links = self._discover_links(page, current_url, base_domain)
                        for link in links:
                            if link not in self.visited_urls:
                                queue.append((link, current_depth + 1))

                except Exception as e:
                    self.logger.warning(f"[!] Skip {current_url}: {str(e)[:60]}")

            browser.close()
        return self.collected_targets

    def _intercept_network(self, request: Request, base_domain: str):
        # 1. กรองเฉพาะสิ่งที่น่าสนใจ และข้ามพวกไฟล์ขยะ/Socket
        ignored_exts = [".js", ".css", ".png", ".jpg", ".svg", ".woff"]
        if request.resource_type not in ["fetch", "xhr"] or any(request.url.split('?')[0].endswith(ext) for ext in ignored_exts):
            return

        if urlparse(request.url).netloc == base_domain and "socket.io" not in request.url:
            params = {}
            content_type = "form"
            
            try:
                # --- ดักจับพารามิเตอร์จาก URL (Query String) ---
                query_params = parse_qs(urlparse(request.url).query)
                if query_params:
                    params.update({k: v[0] for k, v in query_params.items()})

                # --- ดักจับพารามิเตอร์จาก Body ---
                post_data = request.post_data
                if post_data:
                    header_ct = request.headers.get("content-type", "").lower()
                    
                    if "application/json" in header_ct:
                        params.update(json.loads(post_data))
                        content_type = "json"
                    else:
                        body_params = {k: v[0] for k, v in parse_qs(post_data).items()}
                        params.update(body_params)

            except Exception as e:
                self.logger.debug(f"[-] Intercept parse error: {e}")

            # 2. บันทึก Target เฉพาะที่มีพารามิเตอร์ (เพื่อลด Noise ในการสแกน)
            if params:
                # เพิ่มการเก็บ Headers ที่จำเป็น (เช่น Token) ถ้าคุณทำระบบ Persistence ไว้
                self._save_target(
                    url=request.url.split('?')[0], # เก็บเฉพาะ Base URL
                    params=params, 
                    method=request.method, 
                    content_type=content_type
                )
                self.logger.info(f"    [Intercepted API] {request.method} {request.url[:50]}... ({len(params)} params)")

    def _smart_form_filler(self, page: Page):
        """เติมข้อมูลในฟอร์มอัตโนมัติ เพื่อกระตุ้นให้เกิด Network Traffic"""
        inputs = page.query_selector_all("input:visible")
        for inp in inputs:
            try:
                i_type = inp.get_attribute("type") or ""
                # เติมค่าที่ 'สมเหตุสมผล' เพื่อให้ผ่าน Validation ของ Frontend
                if "email" in i_type or "user" in inp.get_attribute("id"):
                    inp.fill("admin@test.local")
                elif "password" in i_type:
                    inp.fill("Password123!")
                else:
                    inp.fill("pentest_test")
            except: continue
        
        # พยายามกดปุ่มที่น่าจะเป็นปุ่ม Submit
        try:
            page.locator("button[type='submit'], button:has-text('Log'), button:has-text('Search')").first.click(timeout=1000)
        except: pass

    def _process_page(self, page: Page, url: str) -> dict:
        # เพิ่มการรอให้ Component ของ Angular โหลดเสร็จจริง
        try:
            page.wait_for_selector("mat-card, form, input[name='email']", timeout=5000)
        except: pass
        
        # 1. ให้เวลามันหายใจหน่อย (เพิ่มเวลาเป็น 3-5 วินาที สำหรับ localhost ที่ช้า)
        page.wait_for_timeout(3000) 
        
        params = {}
        # 2. ปรับ Selector ให้เบสิกที่สุดเพื่อเช็คว่าเจอมั้ย
        elements = page.query_selector_all("input, textarea, select")
        
        for i, el in enumerate(elements):
            try:
                # ข้ามปุ่มและ hidden (ยกเว้นพวกรหัสผ่านหรือ text)
                type_attr = el.get_attribute("type") or ""
                if type_attr in ["submit", "button", "hidden"]: 
                    continue

                name = (el.get_attribute("name") or 
                        el.get_attribute("id") or 
                        el.get_attribute("placeholder") or 
                        f"input_{i}")
                
                # เก็บค่าแบบ Simple ก่อนเพื่อเช็คการทำงาน
                params[name] = {"value": ""} 
            except: continue
            
        return params
    
    def _save_target(self, url: str, params: dict, method: str):
        parsed = urlparse(url)
        path = parsed.path if parsed.path else "/"
        if not self.deduplicator.is_seen(method, path, params):
            self.collected_targets.append({
                "url": url.split('?')[0],
                "method": method,
                "params": params,
                "content_type": "form",  # <--- เพิ่มบรรทัดนี้เข้าไป
                "context": "html_body"
            })
            self.logger.info(f"     [+] Discovered: {method} {path} {list(params.keys())}")


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