import time
from playwright.sync_api import sync_playwright, Page, Request
from src.scanner.deduplicator import Deduplicator
from src.core.logger import setup_logger
from urllib.parse import urlparse, urljoin

class Target:
    def __init__(self, url, method, content_type, params):
        self.url = url
        self.method = method
        self.content_type = content_type
        self.params = params

class Crawler:
    def __init__(self, logger=None):
        self.deduplicator = Deduplicator()
        self.logger = logger or setup_logger("Crawler")
        self.collected_targets = []
        self.visited_urls = set()

    def crawl(self, start_url: str, max_depth: int = 2):
        self.logger.info(f"[Crawler] Starting Crawl on: {start_url} (Depth: {max_depth})")
        base_domain = urlparse(start_url).netloc
        queue = [(start_url, 0)]

        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)
            context = browser.new_context(ignore_https_errors=True)
            page = context.new_page()

            # Event-Driven API Discovery
            page.on("request", lambda req: self._intercept_network(req, base_domain))

            while queue:
                current_url, current_depth = queue.pop(0) 
                
                if current_url in self.visited_urls or self._is_static_resource(current_url):
                    continue
                if current_depth > max_depth:
                    continue

                self.visited_urls.add(current_url)

                try:
                    # โหลดหน้าเว็บและเก็บข้อมูล Forms/URL Params
                    # Note: _process_page ถูกเรียกใช้งานภายในนี้
                    response = page.goto(current_url, wait_until="domcontentloaded", timeout=15000)
                    
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
                                if link not in self.visited_urls:
                                    queue.append((link, current_depth + 1))

                except Exception as e:
                    self.logger.debug(f"[-] Skip {current_url}: {e}")

            browser.close()
        return self.collected_targets

    # --- Core Logic Functions ---

    def _save_target(self, url: str, params: dict, method: str = "GET", content_type: str = "form"):
        base_url = url.split("?")[0].split("#")[0]
        method = method.upper() # Fix: Ensure it's string
        
        sig = f"{method}|{base_url}|{sorted(params.keys())}"

        if not self.deduplicator.is_seen(sig):
            self.deduplicator.add(sig)
            target = Target(
                url=base_url,
                method=method,
                content_type=content_type,
                params=params
            )
            self.collected_targets.append(target)
            self.logger.info(f"     [+] Target Discovered: {method} {base_url} ({len(params)} params)")

    def _intercept_network(self, request: Request, base_domain: str):
        if request.resource_type in ["fetch", "xhr"]:
            url = request.url
            if urlparse(url).netloc == base_domain:
                method = request.method
                c_type = request.headers.get("content-type", "form")
                
                # พยายามวิเคราะห์ Body เบื้องต้น (Pentest Hack)
                params = {}
                try:
                    # ถ้าเป็น JSON ลองแกะหา Key
                    if "json" in c_type.lower() and request.post_data:
                        import json
                        params = {k: "val" for k in json.loads(request.post_data).keys()}
                except:
                    params = {"api_payload": "fuzz_target"}

                self._save_target(url, params, method, "json" if "json" in c_type else "form")

    def _process_page(self, page: Page, url: str) -> dict:
        """รวมรวบ Parameter จากทุกแหล่งในหน้าเดียว"""
        all_params = {}
        all_params.update(self._extract_url_params(url))
        all_params.update(self._extract_form_params(page))
        # คุณสามารถเพิ่ม _extract_forms_and_inputs (POST) เข้ามาเสริมได้ที่นี่
        return all_params

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
                if not href or href.startswith(("#", "javascript:", "mailto:")):
                    continue
                full_url = urljoin(current_url, href)
                clean_url = full_url.split("?")[0].split("#")[0]
                if urlparse(clean_url).netloc == allowed_domain:
                    links_found.add(clean_url)
            except: continue
        return links_found