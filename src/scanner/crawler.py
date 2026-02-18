import json
import re
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
        self.logger.info(f"[Crawler] Starting Crawl on: {start_url}")
        base_domain = urlparse(start_url).netloc
        queue = [(start_url, 0)]
        
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=False) # สังเกตการทำงานได้
            context = browser.new_context(ignore_https_errors=True)

            while queue:
                current_url, current_depth = queue.pop(0)
                
                # 1. กรองไฟล์ Static และ URL ที่เคยไปแล้ว
                if is_static_resource(current_url) or current_url in self.visited_urls:
                    continue
                if current_depth > max_depth: continue
                
                self.visited_urls.add(current_url)

                page = context.new_page()
                page.on("request", lambda req: self._intercept_network(req, base_domain))
                page.on("response", self._intercept_response_leak)

                try:
                    self.auth_handler.apply_session(context)
                    # 2. เข้าหน้าเว็บ (เพิ่มความทนทานต่อ Timeout)
                    self.logger.debug(f"[*] Visiting: {current_url}")
                    page.goto(current_url, wait_until="domcontentloaded", timeout=25000)
                    
                    if page.locator('input[type="password"]').count() > 0 and not self.is_authenticated:
                        self.logger.info(f"[*] Login form detected at {current_url}")
                        
                        success = False
                        # 1. ลอง Login ด้วย Credential ที่ผู้ใช้ให้มา
                        if self.credential:
                            success = self.auth_handler.find_and_login(page, self.credential)
                        
                        # 2. ถ้าไม่สำเร็จ/ไม่มีรหัส ลองใช้ SQLi Bypass หรือรหัสพื้นฐาน (Aggressive)
                        if not success:
                            success = self.auth_handler.aggressive_entry(page)
                        
                        if success:
                            self.is_authenticated = True
                            self.auth_handler._capture_session(page)
                            self.logger.info("[+] Login Successful! Restarting discovery for internal pages...")
                            
                            # --- RECURSIVE DISCOVERY LOGIC ---
                            # ล้างประวัติเพื่อให้ Crawler ยอมกลับไปขุดหน้าเดิมแต่ด้วยสิทธิ์ User
                            self.visited_urls.clear()
                            # ใส่ start_url กลับไปที่ต้นคิว
                            queue.insert(0, (start_url, 0))
                            
                            page.close()
                            continue # ข้ามรอบนี้ไปเริ่มใหม่จากจุดเริ่มพร้อม Session

                    # [DISCOVERY PHASE]
                    dismiss_obstacles(page)
                    
                    # 1. สกัดพารามิเตอร์จาก HTML (DOM)
                    found_params = self._process_page(page, current_url)
                    if found_params:
                        self._save_target(current_url, found_params, "GET", "form")

                    # 2. ขุด Endpoint ลับจากไฟล์ JS
                    self._extract_from_js_static(page, base_domain)

                    # 3. ลองกดปุ่ม/กรอกข้อมูล เพื่อกระตุ้น API Call
                    self._trigger_smart_interaction(page)

                    # [FIND LINKS TO NEXT PAGES]
                    if current_depth < max_depth:
                        links = self._discover_links(page, current_url, base_domain)
                        for link in links:
                            if link not in self.visited_urls:
                                queue.append((link, current_depth + 1))

                except Exception as e:
                    self.logger.warning(f"[!] Skip {current_url}: {str(e)[:60]}")
                finally:
                    # ปิดหน้าเสมอเพื่อป้องกัน Memory Leak
                    page.close()

            browser.close()
        return self.collected_targets

    def _intercept_network(self, request: Request, base_domain: str):
        # กรอง Noise จาก Library ระบบ หรือไฟล์รูปภาพ
        if any(x in request.url for x in ["socket.io", ".woff", ".svg", ".png", ".jpg"]):
            return
        
        if request.resource_type in ["fetch", "xhr", "document"]:
            parsed_url = urlparse(request.url)
            if parsed_url.netloc == base_domain:
                method = request.method.upper()
                params = {}
                content_type = "form"

                # ดักจับพารามิเตอร์จาก URL
                query_params = parse_qs(parsed_url.query)
                if query_params:
                    params.update({k: v[0] for k, v in query_params.items()})

                # ดักจับพารามิเตอร์จาก Body (JSON/Form)
                post_data = request.post_data
                if post_data:
                    ct_header = request.headers.get("content-type", "").lower()
                    if "application/json" in ct_header:
                        try:
                            params.update(json.loads(post_data))
                            content_type = "json"
                        except: pass
                    else:
                        try:
                            params.update({k: v[0] for k, v in parse_qs(post_data).items()})
                        except: pass

                if params or method in ["POST", "PUT", "DELETE"]:
                    clean_url = normalize_url(request.url)
                    self._save_target(clean_url, params, method, content_type)

    def _save_target(self, url: str, params: dict, method: str, c_type: str):
        parsed = urlparse(url)
        path = parsed.path if parsed.path else "/"
        if not self.deduplicator.is_seen(method, path, params):
            self.collected_targets.append({
                "url": url.split('?')[0],
                "method": method,
                "params": params,
                "content_type": c_type,
                "context": "dynamic_intercept" if c_type == "json" else "html_body"
            })
            self.logger.info(f"     [+] Discovered: {method} {path} {list(params.keys())}")

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
    
    def _trigger_smart_interaction(self, page: Page):
        """[FUNCTION 1] กระตุ้นการทำงานของ API ที่ซ่อนอยู่หลังปุ่มหรือฟอร์ม"""
        self.logger.info("    [..] Triggering smart interactions to discover APIs...")
        
        # 1. ค้นหาและลองกรอกข้อมูลใน Input ทุกตัว (เพื่อให้ Event listener ทำงาน)
        try:
            inputs = page.locator("input:visible, textarea:visible").all()
            for i, inp in enumerate(inputs[:10]): # จำกัดเพื่อความเร็ว
                inp.fill(f"test_data_{i}")
        except: pass

        # 2. ลองคลิกปุ่มที่มีโอกาสเรียก API (ข้ามปุ่ม Logout)
        try:
            buttons = page.locator("button:visible, [role='button']").all()
            for btn in buttons[:5]:
                # ข้ามปุ่มที่อาจทำให้ Session หลุด
                text = btn.inner_text().lower()
                if any(x in text for x in ["logout", "signout", "exit", "ออกจากระบบ"]): continue
                
                btn.click(timeout=1000)
                page.wait_for_timeout(500) # รอให้ Network ทำงาน
        except: pass

    def _extract_from_js_static(self, page, base_domain):
        """[FUNCTION 2] ขุดหา Endpoint ลับจากไฟล์ JavaScript (Static Analysis)"""
        self.logger.info("    [..] Extracting endpoints from JS files...")
        
        scripts = page.evaluate("""() => Array.from(document.scripts).map(s => s.src).filter(src => src)""")
        
        for js_url in scripts:
            if urlparse(js_url).netloc == base_domain:
                try:
                    res = self.requester.send("GET", js_url)
                    # Regex ค้นหา Path ที่ขึ้นต้นด้วย /api หรือคำที่น่าสนใจ
                    pattern = r'\"(\/[\w\d\-\.\/\{\}]+)\"|\'(\/[\w\d\-\.\/\{\}]+)\''
                    found = re.findall(pattern, res.text)
                    for matches in found:
                        for path in matches:
                            if path and len(path) > 2 and any(x in path for x in ["/api", "v1", "v2", ".php", ".json"]):
                                # บันทึกเป็น GET endpoint พื้นฐานไว้ก่อน
                                self._save_target(urljoin(page.url, path), {}, "GET", "json")
                except: pass

    def _intercept_response_leak(self, response):
        """[FUNCTION 3] ตรวจสอบข้อมูลหลุดใน Response (Sensitive Data Exposure)"""
        try:
            if "application/json" in response.headers.get("content-type", ""):
                body = response.text()
                # ตัวอย่าง: ตรวจหา Email หรือรูปแบบเลขบัตร (Generic Pattern)
                if re.search(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', body):
                    self.logger.warning(f"    [!] Potential PII Leak (Email) found in API: {response.url}")
        except: pass