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

    def crawl(self, start_url: str, max_depth: int = 3):
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
                
                if clean_url in self.visited_urls or is_static_resource(current_url):
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
        # 1. รอให้ SPA (Angular/React) Render ให้เสร็จ
        try:
            page.wait_for_selector("input, button, form", timeout=3000)
        except: pass

        parsed_url = urlparse(url)
        params = {}
        
        # 2. คัดกรอง Input เฉพาะที่มองเห็นและไม่ได้ซ่อนไว้
        selectors = "input:not([type='submit']), textarea, select"
        elements = page.query_selector_all(selectors)
        
        for i, el in enumerate(elements):
            try:
                name = (el.get_attribute("name") or 
                        el.get_attribute("id") or 
                        el.get_attribute("placeholder") or 
                        f"input_{i}")
                
                # 3. วิเคราะห์ Context (พารามิเตอร์นี้อยู่ที่ไหนใน DOM?)
                # ถ้าอยู่ในหน้าหลัก (Nav) หรือ Footer มักจะเป็น Global Param
                is_global = el.evaluate("""node => {
                    const nav = node.closest('nav, header, footer');
                    return nav !== null;
                }""")

                params[name] = {
                    "value": "",
                    "is_global": is_global,
                    "selector": f"#{el.get_attribute('id')}" if el.get_attribute("id") else name
                }
            except: continue

        # 4. ตรวจสอบความซ้ำซ้อนก่อนส่งไปสแกน
        if params and self.deduplicator.is_seen("GET", parsed_url.path, params):
            self.logger.debug(f"[Crawler] Skipping duplicate structure at {parsed_url.path}")
            return {}

        return params

    def _save_target(self, url: str, params: dict, method: str = "GET", content_type: str = "form"):
        """
        บันทึกเป้าหมายที่พบ โดยใช้ Deduplicator ตรวจสอบความซ้ำซ้อนของโครงสร้างพารามิเตอร์
        """
        # 1. เตรียมข้อมูลพื้นฐาน
        parsed_url = urlparse(url)
        # ตัด Query String และ Fragment ออกเพื่อหา Base Path
        base_url = f"{parsed_url.scheme}://{parsed_url.netloc}{parsed_url.path}"
        url_path = parsed_url.path
        method = method.upper()

        # 2. ตรวจสอบความซ้ำซ้อนผ่าน Deduplicator 
        # (ใช้ is_seen ที่เราแก้ใหม่ ซึ่งรับค่า method, path, และ params)
        if not self.deduplicator.is_seen(method, url_path, params):
            
            # 3. วิเคราะห์ Context เพิ่มเติม (Optional: เพื่อให้ Scanner ทำงานแม่นขึ้น)
            # เราสามารถแยกได้ว่าพารามิเตอร์ไหนเป็น Global จากข้อมูลที่เก็บมาใน _process_page
            
            target_data = {
                "url": base_url, 
                "method": method, 
                "content_type": content_type, 
                "params": params,
                "context": "html_body" # ค่าเริ่มต้น หรือจะปรับตามที่ process_page ส่งมา
            }

            self.collected_targets.append(target_data)
            
            # เก็บ Log เฉพาะตัวที่เพิ่มใหม่
            param_names = list(params.keys())
            self.logger.info(f"     [+] Discovered New Structure: {method} {url_path} {param_names}")
        else:
            self.logger.debug(f"     [-] Duplicate Structure Blocked: {url_path} with params {list(params.keys())}")

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