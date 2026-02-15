import json

from playwright.sync_api import sync_playwright, Page, Request

from src.scanner.deduplicator import Deduplicator
from src.scanner.auth_handler import AuthHandler
from src.core.logger import setup_logger
from urllib.parse import urlparse, urljoin

class Crawler:
    def __init__(self, cred: dict, logger=None):
        self.deduplicator = Deduplicator()
        self.logger = logger or setup_logger("Crawler")
        self.collected_targets = []
        self.visited_urls = set()
        self.auth_handler = AuthHandler()
        self.is_authenticated = False
        self.credential = cred

    def _clear_popups(self, page: Page):
        """ฟังก์ชันในการจัดการ pop-up, modals และ cookie banners"""
        # 1. รายการ Selector ยอดนิยมสำหรับปุ่มปิด หรือยอมรับ
        common_selectors = [
            "button:has-text('Accept')", "button:has-text('ยอมรับ')", 
            "button:has-text('OK')", "button:has-text('ตกลง')",
            "button:has-text('Close')", "button:has-text('ปิด')",
            "button[aria-label*='Close']", ".modal-close", ".close-button",
            "[class*='cookie'] button", "[id*='cookie'] button"
        ]

        # 2. ลองคลิกปุ่มที่เจอก่อน (Soft Clear)
        for selector in common_selectors:
            try:
                element = page.locator(selector).first
                if element.is_visible(timeout=300): # ใช้ Timeout ต่ำมากเพื่อความเร็ว
                    element.click()
                    self.logger.debug(f"[Crawler] Clicked popup/cookie button: {selector}")
            except:
                continue

        # 3. Aggressive Clear: ใช้ JavaScript ลบ Overlay ที่บังหน้าจอทิ้ง (Hard Clear)
        # ป้องกันกรณี Modal ไม่มีปุ่มปิด หรือปุ่มกดยาก
        aggressive_script = """
        () => {
            const overlaySelectors = [
                '[class*="modal"]', '[class*="popup"]', '[class*="overlay"]', 
                '[id*="modal"]', '[id*="popup"]', '.fade.show'
            ];
            overlaySelectors.forEach(s => {
                document.querySelectorAll(s).forEach(el => {
                    // ลบทิ้งเฉพาะตัวที่บังหน้าจอ (มี z-index สูง)
                    const style = window.getComputedStyle(el);
                    if (parseInt(style.zIndex) > 0 || style.position === 'fixed') {
                        el.remove();
                    }
                });
            });
            // ปลดล็อค Scroll ของหน้าเว็บเผื่อโดนล็อคไว้ขณะ Modal เปิด
            document.body.style.overflow = 'auto';
            document.documentElement.style.overflow = 'auto';
        }
        """
        try:
            page.evaluate(aggressive_script)
        except Exception as e:
            self.logger.debug(f"[-] Aggressive clear failed: {e}")

    def crawl(self, start_url: str, max_depth: int = 2):
        self.logger.info(f"[Crawler] Starting Crawl on: {start_url} (Depth: {max_depth})")
        base_domain = urlparse(start_url).netloc
        queue = [(start_url, 0)]
        
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)
            context = browser.new_context(ignore_https_errors=True)
            page = context.new_page()

            # Event-Driven API Discovery
            page.on("dialog", lambda d: d.accept())
            page.on("request", lambda req: self._intercept_network(req, base_domain))

            while queue:
                current_url, current_depth = queue.pop(0) 

                clean_url_for_visited = current_url.split('?')[0]
                if current_url in self.visited_urls or self._is_static_resource(current_url):
                    continue
                if current_depth > max_depth:
                    continue

                self.visited_urls.add(clean_url_for_visited)

                try:

                    # โหลดหน้าเว็บและเก็บข้อมูล Forms/URL Params
                    # Note: _process_page ถูกเรียกใช้งานภายในนี้
                    response = page.goto(current_url, wait_until="domcontentloaded", timeout=15000)

                    self._clear_popups(page)
                    page.wait_for_timeout(1000)

                    # --- [NEW] Discovery Auth Logic ---
                    # ถ้ายังไม่ได้ Login และมี Credential มา ให้พยายามหาทาง Login ในทุกหน้าที่ผ่านไป
                    if not self.is_authenticated and self.credential:
                        if self.auth_handler.find_and_login(page, self.credential):
                            self.is_authenticated = True
                            self._clear_popups(page)
                            queue.insert(0, (page.url, current_depth))
                            continue

                    # --- [NEW] Check Session Timeout ---
                    # ถ้าเคย Login แล้ว แต่อยู่ดีๆ หน้า Login โผล่มา ให้ Login ซ้ำ
                    if self.is_authenticated and page.locator('input[type="password"]').is_visible():
                        self.auth_handler.login_with_heuristics(page, self.credential)
                    
                    if response and response.status < 400:
                        # ดึงข้อมูลจาก Page Content
                        found_params = self._process_page(page, current_url)
                        
                        # บันทึก Target จากสิ่งที่เจอในหน้า HTML
                        if found_params:
                            self._save_target(current_url, found_params, "GET")

                        # หา Link เพื่อไปหน้าถัดไป
                        if current_depth < max_depth:
                            links = self._discover_links(page, current_url, base_domain)
                            for link in links:
                                if link.split('?')[0] not in self.visited_urls:
                                    queue.append((link, current_depth + 1))

                except Exception as e:
                    self.logger.debug(f"[-] Skip {current_url}: {e}")

            browser.close()
        return self.collected_targets

    # --- Core Logic Functions ---

    def _save_target(self, url: str, params: dict, method: str = "GET", content_type: str = "form"):
        base_url = url.split("?")[0]
        method = method.upper() 
        sig = f"{method}|{base_url}|{sorted(params.keys())}"

        if not self.deduplicator.is_seen(sig):
            self.deduplicator.add(sig)
            target = {
                "url": base_url,
                "method": method,
                "content_type": content_type,
                "params": params
            }
            self.collected_targets.append(target)
            self.logger.info(f"     [+] Target Discovered: {method} {base_url} ({len(params)} params)")

    def _intercept_network(self, request: Request, base_domain: str):
        if request.resource_type in ["fetch", "xhr"]:
            url = request.url
            if urlparse(url).netloc == base_domain:
                params = {}
                try:
                    if request.post_data:
                        params = {k: "val" for k in json.loads(request.post_data).keys()}
                except: pass
                
                self._save_target(url, params, request.method, "json")

    def _process_page(self, page: Page, url: str) -> dict:
        params = {}
        # ดึงจาก URL
        if "?" in url:
            query = urlparse(url).query
            for pair in query.split("&"):
                if "=" in pair:
                    k, v = pair.split("=", 1)
                    params[k] = v
        
        # ดึงจาก Form inputs
        inputs = page.query_selector_all("input:not([type='hidden'])")
        for i, el in enumerate(inputs):
            name = el.get_attribute("name") or el.get_attribute("id") or f"input_{i}"
            params[name] = "test"
            
        return params

    # --- Utility Functions (เหมือนเดิมที่คุณเขียนไว้) ---

    def _is_static_resource(self, url: str) -> bool:
        extensions = ('.jpg', '.jpeg', '.png', '.gif', '.css', '.woff', '.woff2', '.pdf', '.zip', '.svg')
        return url.lower().endswith(extensions)

    def _extract_url_params(self, current_url: str) -> dict:
        params = {}
        if "?" in current_url:
            try:
                query = urlparse(current_url).query
                for pair in query.split("&"):
                    if "=" in pair:
                        key, val = pair.split("=", 1)
                        params[key] = val
            except: pass
        return params

    def _extract_form_params(self, page: Page) -> dict:
        params = {}
        elements = page.query_selector_all("input:not([type='hidden']), textarea, select")
        for i, el in enumerate(elements):
            try:
                p_name = el.get_attribute("name") or el.get_attribute("id") or f"anonymous_input_{i+1}"
                params[p_name] = "test_value"
            except: continue
        return params

    def _discover_links(self, page: Page, current_url: str, allowed_domain: str) -> set:
        links_found = set()

        elements = page.query_selector_all("a[href]")

        for el in elements:
            try:
                href = el.get_attribute("href")
                if not href or href.startswith(("javascript:", "mailto:")):
                    continue
                full_url = urljoin(current_url, href)

                if urlparse(full_url).netloc == allowed_domain:
                    links_found.add(full_url)
            except: continue

        buttons = page.query_selector_all("button, [role='button'], .mat-menu-item")
        for btn in buttons:
            try:
                # ถ้ามีข้อความน่าสนใจ เช่น Login, Register, Search ให้เก็บไว้ใน Log 
                # หรือถ้าแอปใช้ Path ใน Attribute อื่นๆ
                attr = btn.get_attribute("routerlink") or btn.get_attribute("href")
                if attr:
                    full_url = urljoin(current_url, attr)
                    links_found.add(full_url)
            except: continue
        return links_found