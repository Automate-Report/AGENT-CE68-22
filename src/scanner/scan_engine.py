import io
import logging
import json
import requests
from requests.exceptions import RequestException
from urllib.parse import urlparse

from src.scanner.crawler import Crawler
from src.exploits.xss.scanner import XSSScanner
from src.exploits.xss.dom_scanner import DOMScanner
from src.exploits.sqli.scanner import SQLiScanner
from src.core.logger import setup_logger
from src.networking.requester import Requester
from src.utils.url_helper import normalize_url

class ScanOrchestrator:
    def __init__(self, job_data: dict):
        self.job_id = job_data.get("job_id")
        self.target = job_data.get("target_url")
        self.attack_type = job_data.get("attack_type")
        self.cred = job_data.get("credential")

        self.logger = setup_logger(f"ScanEngine-{self.job_id}")
        
        # Init Tools
        self.requester = Requester(logger=self.logger)
        self.crawler = Crawler(logger=self.logger, cred=self.cred)
        self.reflected_scanner = XSSScanner(logger=self.logger) 
        self.dom_scanner = DOMScanner(logger=self.logger)
        self.sqli_scanner = SQLiScanner(logger=self.logger)

        # Logger Capture Setup
        self.log_capture = io.StringIO()
        self.capture_handler = logging.StreamHandler(self.log_capture)
        formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', '%H:%M:%S')
        self.capture_handler.setFormatter(formatter)
        self.logger.addHandler(self.capture_handler)
        
        # Session state tracking
        self.session_state = {
            "authenticated": False,
            "cookies": None,
            "auth_info": {}
        }

    # ===== PHASE 1: CHECK REACHABILITY =====
    def check_reachability(self) -> tuple[bool, str]:
        """
        Phase 1: Verify the target is reachable and responsive
        Returns: (success: bool, message: str)
        """
        self.logger.info("=" * 60)
        self.logger.info("[PHASE 1] CHECKING TARGET REACHABILITY")
        self.logger.info("=" * 60)
        
        try:
            self.logger.info(f"🔍 Testing connectivity to {self.target}...")
            response = requests.head(self.target, timeout=10, allow_redirects=True, verify=False)
            
            if response.status_code < 400:
                self.logger.info(f"✅ Target is reachable! (Status: {response.status_code})")
                return True, f"Reachable - HTTP {response.status_code}"
            else:
                msg = f"Target returned error status: {response.status_code}"
                self.logger.warning(f"⚠️ {msg}")
                return False, msg
                
        except requests.exceptions.Timeout:
            msg = "Connection timeout - target took too long to respond"
            self.logger.error(f"❌ {msg}")
            return False, msg
        except requests.exceptions.ConnectionError:
            msg = "Connection failed - cannot reach target"
            self.logger.error(f"❌ {msg}")
            return False, msg
        except RequestException as e:
            msg = f"Connection error: {str(e)}"
            self.logger.error(f"❌ {msg}")
            return False, msg

    # ===== PHASE 2: FORCE LOGIN =====
    async def force_login(self) -> bool:
        """
        Phase 2: Attempt to authenticate to the application
        - Try with provided credentials if available
        - Try aggressive login methods if standard fails
        Returns: success (bool)
        """
        self.logger.info("=" * 60)
        self.logger.info("[PHASE 2] AUTHENTICATION / FORCED LOGIN")
        self.logger.info("=" * 60)
        
        try:
            async with self.crawler.get_browser_context() as context:
                page = await context.new_page()
                
                try:
                    self.logger.info(f"🌐 Loading target page: {self.target}")
                    await page.goto(self.target, wait_until="networkidle", timeout=15000)
                    self.logger.info(f"✅ Page loaded successfully")
                    
                except Exception as e:
                    self.logger.error(f"❌ Failed to load page: {str(e)}")
                    await page.close()
                    return False
                
                password_exists = await page.locator('input[type="password"]').count() > 0
    
                if not password_exists:
                    self.logger.info("🕵️ No login form on landing page, searching for entry...")
                    # ลองเดา Path มาตรฐาน (Generic Guessing)
                    common_login_paths = ["/login", "/signin", "/#/login", "/#/signin"]
                    
                    # ลองหาปุ่ม Login ในหน้าเว็บก่อน
                    login_btn = page.locator('a:has-text("Login"), button:has-text("Login"), a:has-text("Sign in")').first
                    if await login_btn.is_visible():
                        await login_btn.click()
                        await page.wait_for_load_state("networkidle")
                    else:
                        # ถ้าหาปุ่มไม่เจอ ให้ลองเติม Path เอง (Adaptive Navigation)
                        base_url = self.target.rstrip('/')
                        for path in common_login_paths:
                            try:
                                self.logger.info(f"Trying login path: {path}")
                                await page.goto(f"{base_url}{path}", wait_until="networkidle", timeout=5000)
                                if await page.locator('input[type="password"]').count() > 0:
                                    self.logger.info(f"✅ Found login form at {page.url}")
                                    break
                            except: continue
                
                # Try authentication if credentials provided
                login_success = False
                if self.cred and isinstance(self.cred, dict):
                    self.logger.info(f"🔐 Attempting login with provided credentials...")
                    try:
                        login_success = await self.crawler.auth_handler.find_and_login(page, self.cred)
                        if login_success:
                            self.logger.info(f"✅ Login successful with provided credentials!")
                    except Exception as e:
                        self.logger.warning(f"⚠️ Heuristic login failed: {str(e)}")
                
                # Try aggressive login if standard login failed
                if not login_success:
                    self.logger.info(f"🔨 Attempting aggressive login (SQLi bypass, default creds)...")
                    try:
                        login_success = await self.crawler.auth_handler.aggressive_entry(page)
                        if login_success:
                            self.logger.info(f"✅ Aggressive login successful!")
                    except Exception as e:
                        self.logger.warning(f"⚠️ Aggressive login failed: {str(e)}")
                
                # Capture session cookies/tokens
                cookies = await context.cookies()
                if cookies:
                    self.session_state["cookies"] = cookies
                    self.session_state["authenticated"] = True
                    self.logger.info(f"🍪 Captured {len(cookies)} session cookies")
                else:
                    self.logger.warning(f"⚠️ No cookies captured")
                
                # Store auth info for scanners
                self.session_state["auth_info"] = {
                    "cookies": cookies,
                    "auth_token": getattr(self.crawler.auth_handler, 'auth_token', None)
                }
                
                await page.close()
                return login_success
                
        except Exception as e:
            self.logger.error(f"❌ Critical error during authentication: {str(e)}")
            return False

    # ===== PHASE 3: CRAWL APPLICATION =====
    async def crawl_url(self) -> list:
        """
        Phase 3: Discover all crawlable endpoints and parameters
        Returns: list of target endpoints
        """
        self.logger.info("=" * 60)
        self.logger.info("[PHASE 3] DISCOVERY / CRAWLING")
        self.logger.info("=" * 60)
        
        try:
            self.logger.info(f"🕷️ Starting crawl of {self.target}...")
            crawled_targets = await self.crawler.crawl(self.target)
            
            if not crawled_targets:
                self.logger.warning("⚠️ No endpoints discovered during crawl")
                # Fallback: scan entry point
                crawled_targets = [{
                    "url": self.target,
                    "method": "GET",
                    "params": {},
                    "content_type": "form"
                }]
            
            # Clean and normalize URLs
            cleaned_urls = []
            for target in crawled_targets:
                try:
                    target["url"] = normalize_url(target["url"])
                    cleaned_urls.append(target["url"])
                except Exception as e:
                    self.logger.debug(f"Failed to normalize URL: {e}")
            
            self.logger.info(f"✅ Crawl complete. Discovered {len(crawled_targets)} endpoints")
            for url in cleaned_urls[:10]:  # Show first 10
                self.logger.info(f"   - {url}")
            if len(cleaned_urls) > 10:
                self.logger.info(f"   ... and {len(cleaned_urls) - 10} more")
            
            return crawled_targets
            
        except Exception as e:
            self.logger.error(f"❌ Crawling failed: {str(e)}")
            return []

    # ===== PHASE 4: ATTACK & EXPLOIT =====
    async def attack(self, targets: list) -> list:
        """
        Phase 4: Execute attacks (XSS and/or SQLi) on discovered endpoints
        Returns: list of findings
        """
        self.logger.info("=" * 60)
        self.logger.info("[PHASE 4] ATTACK / EXPLOITATION")
        self.logger.info("=" * 60)

        findings = []
        
        if not targets:
            self.logger.warning("⚠️ No targets to attack")
            return findings
        
        unique_targets = list({t['url']: t for t in targets}.values())
        self.logger.info(f"📊 Deduplication: {len(targets)} -> {len(unique_targets)} unique targets")
        targets = unique_targets
        
        # Sync session state with scanners
        self._sync_session_to_scanners()
        
        # Execute attack based on type
        if self.attack_type == "sql_injection":
            self.logger.info(f"🔓 Running SQL Injection scans on {len(targets)} endpoints...")
            findings = await self._run_sqli_scan(targets)
            
        elif self.attack_type == "xss" or self.attack_type == "XSS":
            self.logger.info(f"💉 Running XSS scans on {len(targets)} endpoints...")
            findings = await self._run_xss_scan(targets)
            
        elif self.attack_type == "all":
            self.logger.info(f"🎯 Running ALL scans on {len(targets)} endpoints...")
            findings.extend(await self._run_xss_scan(targets))
            findings.extend(await self._run_sqli_scan(targets))
        else:
            self.logger.warning(f"⚠️ Unknown attack type: {self.attack_type}")
        
        if findings:
            self.logger.info(f"✅ Found {len(findings)} vulnerabilities!")
        else:
            self.logger.info(f"✅ No vulnerabilities found")
        
        return findings

    # ===== MAIN WORKFLOW =====
    async def run_workflow(self):
        """
        Execute the complete 4-phase penetration test workflow
        """
        try:
            # PHASE 1: Check Reachability
            is_reachable, reachability_msg = self.check_reachability()
            if not is_reachable:
                return self._build_response("failed", 
                    error=f"Target Unreachable: {reachability_msg}")
            
            self.logger.info("[+] Starting Public Discovery...")
            public_targets = await self.crawler.crawl(self.target, max_depth=1)
            
            # PHASE 2: Force Login
            auth_success = await self.force_login()
            if auth_success:
                # --- PHASE 3: Authenticated Crawl ---
                # เมื่อ Login สำเร็จแล้ว ให้ Crawler วิ่งอีกรอบเพื่อกวาด API ลับข้างใน
                self.logger.info("[+] Starting Authenticated Discovery...")
                # ส่งต่อ Session เข้าไปใน Crawler (เช่น Cookies/LocalStorage)
                auth_targets = await self.crawler.crawl(self.target, max_depth=2)
                
                # รวมผลลัพธ์เข้าด้วยกัน (Deduplicator จะช่วยกรองตัวที่ซ้ำออกให้เอง)
                all_targets = public_targets + auth_targets
            else:
                all_targets = public_targets
            
            # PHASE 4: Attack
            if self.crawler.auth_handler.auth_token: # Token ที่ AuthHandler เก็บมา
                token_data = json.loads(self.crawler.auth_handler.auth_token)
                bearer = token_data.get('token')
                if bearer:
                    self.requester.set_header("Authorization", f"Bearer {bearer}")
                    self.logger.info("[ScanEngine] 🔑 Bearer Token Injected for Phase 4")



            findings = await self.attack(all_targets)
            
            # Build final response
            cleaned_urls = [normalize_url(t["url"]) if isinstance(t, dict) else normalize_url(str(t)) 
                          for t in all_targets]
            
            return self._build_response(
                "found" if findings else "not found",
                findings=findings,
                target_count=len(all_targets),
                crawler_urls=cleaned_urls
            )

        except Exception as e:
            self.logger.error(f"❌ Critical Error: {str(e)}")
            import traceback
            self.logger.error(traceback.format_exc())
            return self._build_response("failed", error=str(e))
        
        finally:
            self._cleanup_logger()

    def _sync_session_to_scanners(self):
        """Sync captured session state to all scanners"""
        if self.session_state["cookies"]:
            self.logger.info("[ScanEngine] Syncing session state to scanners...")
            
            # Format cookies for Requester
            try:
                formatted_cookies = {c['name']: c['value'] for c in self.session_state["cookies"]}
                if hasattr(self.requester, 'set_cookies'):
                    self.requester.set_cookies(formatted_cookies)
            except Exception as e:
                self.logger.warning(f"Could not sync cookies to requester: {e}")
            
            # Sync with XSS scanner verifier
            try:
                if hasattr(self.reflected_scanner, 'verifier'):
                    self.reflected_scanner.verifier.auth_data = self.session_state["auth_info"]
            except Exception as e:
                self.logger.debug(f"Could not sync to XSS verifier: {e}")
            
            # Sync with DOM scanner
            try:
                self.dom_scanner.auth_info = self.session_state["auth_info"]
            except Exception as e:
                self.logger.debug(f"Could not sync to DOM scanner: {e}") 

    def _build_response(self, status, findings=[], target_count=0, error=None, crawler_urls=[]):
        """Build standardized response structure"""
        return {
            "job_id": int(self.job_id),
            "status": status,
            "findings": findings,
            "target_count": target_count,
            "error_log": error,
            "crawler_urls": crawler_urls,
            "execution_logs": self.log_capture.getvalue().splitlines()
        }

    def _cleanup_logger(self):
        """Clean up logger resources"""
        if hasattr(self, 'capture_handler'):
            self.logger.removeHandler(self.capture_handler)
            self.capture_handler.close()

    async def _run_xss_scan(self, targets: list) -> list:
        """Execute XSS scanning on targets"""
        findings = []
        for i, t in enumerate(targets, 1):
            url = t["url"] if isinstance(t, dict) else str(t)
            method = t.get("method", "GET") if isinstance(t, dict) else "GET"
            params = t.get("params", {}) if isinstance(t, dict) else {}
            c_type = t.get("content_type", "form") if isinstance(t, dict) else "form"
            
            self.logger.info(f"[{i}/{len(targets)}] XSS Scan: {method} {url}")
            
            try:
                is_api = any(x in url.lower() for x in ["/rest/", "/api/", ".json"])
                
                # Reflected XSS
                self.logger.debug(f"  └─ Testing Reflected XSS...")
                findings.extend(self.reflected_scanner.scan(url, params, method, c_type))
                
                # DOM XSS (for non-API endpoints)
                # if not is_api:
                #     self.logger.debug(f"  └─ Testing DOM XSS...")
                #     self.dom_scanner.auth_info = self.session_state["auth_info"]
                #     dom_findings = await self.dom_scanner.scan(url, params, method)
                #     findings.extend(dom_findings)
                    
            except Exception as e:
                self.logger.warning(f"  └─ Error scanning {url}: {str(e)}")
        
        return findings

    async def _run_sqli_scan(self, targets: list) -> list:
        """Execute SQL Injection scanning on targets"""
        findings = []
        for i, t in enumerate(targets, 1):
            url = t["url"] if isinstance(t, dict) else str(t)
            method = t.get("method", "GET") if isinstance(t, dict) else "GET"
            params = t.get("params", {}) if isinstance(t, dict) else {}
            c_type = t.get("content_type", "form") if isinstance(t, dict) else "form"
            
            self.logger.info(f"[{i}/{len(targets)}] SQLi Scan: {method} {url}")
            
            try:
                findings.extend(self.sqli_scanner.scan(url, params, method, c_type))
            except Exception as e:
                self.logger.warning(f"  └─ Error scanning {url}: {str(e)}")
        
        return findings