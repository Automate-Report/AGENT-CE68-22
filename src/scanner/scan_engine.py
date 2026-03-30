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
from src.utils.browser_helper import goto_with_retry

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

    # ===== PHASE 2: FORCE LOGIN (Refactored) =====
    async def force_login(self) -> bool:
        self.logger.info("=" * 60)
        self.logger.info("[PHASE 2] AUTHENTICATION / FORCED LOGIN")
        self.logger.info("=" * 60)
        
        try:
            async with self.crawler.get_browser_context() as context:
                page = await context.new_page()
                
                try:
                    self.logger.info(f"🌐 Loading target page: {self.target}")
                    await goto_with_retry(page, self.target, wait_until="networkidle", timeout=15000, logger=self.logger)
                    self.logger.info(f"✅ Page loaded successfully")
                except Exception as e:
                    self.logger.error(f"❌ Failed to load page: {str(e)}")
                    await page.close()
                    return False
                
                # --- ส่วนการหาหน้า Login (เดิมของคุณ) ---
                password_exists = await page.locator('input[type="password"]').count() > 0
                if not password_exists:
                    self.logger.info("🕵️ No login form on landing page, searching for entry...")
                    common_login_paths = ["/login", "/signin", "/#/login", "/#/signin"]
                    login_btn = page.locator('a:has-text("Login"), button:has-text("Login"), a:has-text("Sign in")').first
                    if await login_btn.is_visible():
                        await login_btn.click()
                        await page.wait_for_load_state("load")
                        await page.wait_for_timeout(2000)
                    else:
                        base_url = self.target.rstrip('/')
                        for path in common_login_paths:
                            try:
                                await goto_with_retry(page, f"{base_url}{path}", wait_until="networkidle", timeout=10000, logger=self.logger)
                                if await page.locator('input[type="password"]').count() > 0:
                                    self.logger.info(f"✅ Found login form at {page.url}")
                                    break
                            except: continue

                # --- Login Strategy ---
                login_success = False
                has_creds = bool(
                    self.cred and isinstance(self.cred, dict)
                    and self.cred.get('username') and self.cred.get('password')
                )

                # 1. Standard Login (credential-based)
                self.logger.info(f"[Auth] Attempting Primary Login Method...")
                login_success = await self.crawler.auth_handler.perform_login(page, self.cred)

                # 2. Heuristic Login (ลอง detect form แล้วกรอก creds อีกรอบ)
                if not login_success and has_creds:
                    self.logger.info(f"🔐 Primary failed. Attempting Heuristic Login...")
                    try:
                        login_success = await self.crawler.auth_handler.find_and_login(page, self.cred)
                    except Exception as e:
                        self.logger.warning(f"⚠️ Heuristic login error: {str(e)}")

                # 3. Aggressive Entry (SQLi Bypass + Default Creds)
                #    → เรียกเฉพาะเมื่อไม่มี credentials ใน job เท่านั้น
                #    → ถ้ามี creds แต่ login ไม่ผ่าน = auth fail จริง ไม่ใช่ช่องโหว่ของเว็บ
                if not login_success and not has_creds:
                    self.logger.info(f"🔨 No credentials provided. Attempting Aggressive Entry (SQLi Bypass)...")
                    try:
                        login_success = await self.crawler.auth_handler.aggressive_entry(page)
                    except Exception as e:
                        self.logger.warning(f"⚠️ Aggressive login error: {str(e)}")

                # --- 🚩 จัดการผลลัพธ์หลัง Login ---
                if login_success:
                    # 💡 สำคัญ: ต้อง Capture ข้อมูลก่อนปิด Page
                    await self.crawler.auth_handler._capture_session(page) 
                    
                    cookies = await context.cookies()
                    if cookies:
                        self.session_state["cookies"] = cookies
                        self.session_state["authenticated"] = True
                        self.logger.info(f"🍪 Captured {len(cookies)} session cookies")
                    
                    self.session_state["auth_info"] = {
                        "cookies": cookies,
                        "storage_state": getattr(self.crawler.auth_handler, 'storage_state', None),
                        "auth_token": getattr(self.crawler.auth_handler, 'auth_token', None)
                    }
                    self.logger.info(f"✅ [Auth Success] Current URL: {page.url}")
                else:
                    self.logger.warning("❌ [Auth Failed] Could not authenticate to target")

                await page.close()
                return login_success # 🚩 คืนค่าจริงเพื่อให้ run_workflow ทำงานต่อ
                
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
        self.logger.info("=" * 60)
        self.logger.info("[PHASE 4] ATTACK / EXPLOITATION")
        self.logger.info("=" * 60)

        findings = []
        
        if not targets:
            self.logger.warning("⚠️ No targets to attack")
            return findings
        
        # 🚩 Deduplication Logic (Smart Filter)
        unique_map = {}
        for t in targets:
            p_keys = sorted(t.get('params', {}).keys())
            # สร้าง Key จาก Method + URL + รายชื่อพารามิเตอร์
            key = f"{t.get('method', 'GET')}_{t['url']}_{'-'.join(p_keys)}"
            unique_map[key] = t

        unique_targets = list(unique_map.values())
        self.logger.info(f"📊 Deduplication: {len(targets)} -> {len(unique_targets)} unique targets")
        
        # Sync session state with scanners (Cookies/Tokens)
        self._sync_session_to_scanners()
        
        # 🚩 ใช้ unique_targets ในการสแกนเพื่อความประหยัดเวลาและแม่นยำ
        if self.attack_type in ["sqli", "sql_injection"]:
            self.logger.info(f"🔓 Running SQL Injection scans on {len(unique_targets)} endpoints...")
            findings = await self._run_sqli_scan(unique_targets)
            
        elif self.attack_type in ["xss", "XSS"]:
            self.logger.info(f"💉 Running XSS scans on {len(unique_targets)} endpoints...")
            findings = await self._run_xss_scan(unique_targets)
            
        elif self.attack_type == "all":
            self.logger.info(f"🎯 Running ALL scans on {len(unique_targets)} endpoints...")
            findings.extend(await self._run_xss_scan(unique_targets))
            findings.extend(await self._run_sqli_scan(unique_targets))
        else:
            self.logger.warning(f"⚠️ Unknown attack type: {self.attack_type}")
        
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
            auth_success = await self.force_login() # เรียกฟังก์ชันเดียวจบ

            # ตรวจสอบ Finding จาก Auth (ถ้ามี)
            auth_findings = []
            if hasattr(self.crawler.auth_handler, 'collected_findings'):
                auth_findings = self.crawler.auth_handler.collected_findings
            
            if auth_success:
                # 1. ดึงข้อมูล Session จาก AuthHandler ออกมาจัดการ
                captured_cookies = self.crawler.auth_handler.cookies
                captured_storage = getattr(self.crawler.auth_handler, 'storage_state', None)
                
                if captured_cookies:
                    # ส่งคุกกี้เข้า Crawler สำหรับ Phase 3
                    self.crawler.set_external_cookies(captured_cookies)
                if captured_storage:
                    # ส่ง Storage State (LocalStorage/SessionStorage) เข้า Crawler
                    self.crawler.set_external_storage_state(captured_storage)

                current_url = self.crawler.auth_handler.last_authenticated_url or self.target
    
                self.logger.info("=" * 60)
                self.logger.info(f"[PHASE 3] DEEP CRAWLING WITH SESSION...")
                self.logger.info(f"Seed URL: {current_url}")
                self.logger.info("=" * 60)
                
                # Crawler จะใช้คุกกี้ security=low ที่เราเซ็ตเมื่อครู่
                auth_targets = await self.crawler.crawl(current_url, max_depth=3)

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

            scan_findings = await self.attack(all_targets)
            findings = auth_findings + scan_findings

            if findings:
                self.logger.info(f"✅ Found {len(findings)} vulnerabilities!")
            else:
                self.logger.info(f"✅ No vulnerabilities found")

            is_vuln_found = len(findings) > 0
            # Build final response
            cleaned_urls = [normalize_url(t["url"]) if isinstance(t, dict) else normalize_url(str(t)) 
                          for t in all_targets]
            
            return self._build_response(
                "found" if is_vuln_found else "not found",
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
        current_cookies = self.crawler.auth_handler.cookies
        
        if current_cookies:
            # ส่งคุกกี้ที่แก้เป็น security=low ให้ Requester กลาง
            self.requester.set_cookies(current_cookies)
            
            # 🚩 สำคัญ: ส่ง auth_info ให้ Scanner เพื่อใช้ถ่ายรูป
            auth_payload = {
                "cookies": current_cookies,
                "auth_token": getattr(self.crawler.auth_handler, 'auth_token', None)
            }
            
            if hasattr(self.sqli_scanner, 'auth_info'):
                self.sqli_scanner.auth_info = auth_payload
            if hasattr(self.reflected_scanner, 'auth_info'):
                self.reflected_scanner.auth_info = auth_payload

            self.logger.info("[ScanEngine] 🔄 Global Session Sync Completed (Cookies & Auth Info)")

    def _build_response(self, status, findings=None, target_count=0, error=None, crawler_urls=None):
        """Build standardized response structure"""
        findings = findings if findings is not None else []
        crawler_urls = crawler_urls if crawler_urls is not None else []
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
            url      = t["url"]    if isinstance(t, dict) else str(t)
            method   = t.get("method", "GET")         if isinstance(t, dict) else "GET"
            params   = t.get("params", {})             if isinstance(t, dict) else {}
            c_type   = t.get("content_type", "form")  if isinstance(t, dict) else "form"
            dom_only = t.get("dom_only", False)        if isinstance(t, dict) else False

            # ── Still filter any remaining internal params (safety net) ──────
            scannable_params = {
                k: v for k, v in params.items()
                if self._is_scannable_param(k, url)
            }

            # ── Check response content-type (skip RSC/binary) ────────────────
            if not self._is_html_response(url):
                self.logger.info(f"[{i}/{len(targets)}] ⏭ Skipping {url} — not HTML/JSON response")
                continue

            self.logger.info(f"[{i}/{len(targets)}] {'DOM-Only' if dom_only else 'XSS'} Scan: {method} {url}")

            try:
                # is_api: true if url patterns match, or if the crawler tagged it
                # as a backend API call (different host:port from frontend target),
                # or if the response is application/json (not HTML)
                is_backend_api = t.get("backend_api", False) if isinstance(t, dict) else False
                is_api_path    = any(x in url.lower() for x in ["/rest/", "/api/", ".json"])
                is_json_resp   = self._is_json_response(url)
                is_api         = is_backend_api or is_api_path or is_json_resp

                # Reflected XSS — only if we have real params AND not dom_only
                if scannable_params and not dom_only:
                    self.logger.debug(f"  └─ Testing Reflected XSS ({len(scannable_params)} params)...")
                    findings.extend(await self.reflected_scanner.scan(url, scannable_params, method, c_type))

                # DOM XSS — skip for pure API/JSON endpoints (JSON has no DOM, no sinks)
                if not is_api:
                    self.logger.debug(f"  └─ Testing DOM XSS...")
                    self.dom_scanner.auth_info = self.session_state["auth_info"]
                    dom_findings = await self.dom_scanner.scan(url, scannable_params, method)
                    findings.extend(dom_findings)
                else:
                    self.logger.debug(f"  └─ Skipping DOM XSS (API/JSON endpoint)")

            except Exception as e:
                self.logger.warning(f"  └─ Error scanning {url}: {str(e)}")

        return findings


    # ── Framework-internal parameter filter ────────────────────────────────────
    # These params are generated by JS frameworks and carry no user-controlled
    # data that could be exploited for XSS / SQLi.
    _INTERNAL_PARAM_PREFIXES = ("_rsc", "_next", "__next", "__react", "_vercel", "__cf", "fbclid", "gclid", "utm_")
    _INTERNAL_PARAM_EXACT    = {"_rsc", "_nc_", "__fb", "ref", "source"}

    def _is_scannable_param(self, param_key: str, url: str = "") -> bool:
        """Return True if this parameter is worth scanning (not a framework-internal token)."""
        lk = param_key.lower()
        # Exact match
        if lk in self._INTERNAL_PARAM_EXACT:
            return False
        # Prefix match
        if any(lk.startswith(p) for p in self._INTERNAL_PARAM_PREFIXES):
            return False
        # Looks like a random hash / RSC token (short alphanumeric, no real word)
        if len(lk) <= 6 and lk.isalnum() and not lk.isdigit():
            # Only skip if it's actually in a _rsc=... style URL
            if "_rsc=" in url or "_next=" in url:
                return False
        return True

    def _is_html_response(self, url: str) -> bool:
        """Quick GET check — return False for RSC/binary responses, True for HTML/JSON."""
        try:
            resp = self.requester.send("GET", url, {})
            if resp is None:
                return True
            ct = resp.headers.get("content-type", "").lower()
            if "text/x-component" in ct:
                return False
            if "application/octet-stream" in ct:
                return False
            return True
        except Exception:
            return True

    def _is_json_response(self, url: str) -> bool:
        """Return True if the endpoint returns application/json (pure REST API, no DOM)."""
        try:
            resp = self.requester.send("GET", url, {})
            if resp is None:
                return False
            ct = resp.headers.get("content-type", "").lower()
            return "application/json" in ct
        except Exception:
            return False


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
                findings.extend(await self.sqli_scanner.scan(url, params, method, c_type))
            except Exception as e:
                self.logger.warning(f"  └─ Error scanning {url}: {str(e)}")
        
        return findings