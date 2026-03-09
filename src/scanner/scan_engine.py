import io
import logging
import requests
from requests.exceptions import RequestException
from urllib.parse import urlparse

from src.scanner.crawler import Crawler
from src.exploits.xss.scanner import XSSScanner
from src.exploits.xss.dom_scanner import DOMScanner
from src.exploits.sqli.scanner import SQLiScanner
from src.core.logger import setup_logger
from src.networking.requester import Requester
from src.utils.url_helper import normalize_url # [ADDED] เรียกใช้ Utils

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

    def _is_target_reachable(self, target_url: str, timeout: int = 10) -> tuple[bool, str]:
        try:
            # ใช้ verify=False สำหรับ Internal Test
            response = requests.head(target_url, timeout=timeout, allow_redirects=True, verify=False)
            if response.status_code < 400:
                return True, "Reachable"
            return False, f"Target returned status code: {response.status_code}"
        except RequestException as e:
            return False, f"Connection failed: {str(e)}"

    async def run_workflow(self):
        try:
            # Connectivity Check
            is_up, message = self._is_target_reachable(self.target)
            if not is_up:
                return self._build_response("failed", error=f"Target Unreachable: {message}")
            
            # Login First
            self.logger.info(f"[ScanEngine] Pre-authentication phase on {self.target}")
            # สร้าง Temporary Page เพื่อทำการ Login
            # หมายเหตุ: Crawler ของคุณควรมี method สำหรับเข้าถึง Browser Context ได้
            async with self.crawler.get_browser_context() as context:
                page = await context.new_page()
                await page.goto(self.target, wait_until="networkidle")
                
                # เรียกใช้ AuthHandler ที่เราเตรียมไว้
                # ถ้ามี credential ให้ใช้ heuristic login ถ้าไม่มีให้ลอง aggressive (SQLi Bypass)
                success = False
                if self.cred:
                    success = await self.crawler.auth_handler.find_and_login(page, self.cred)
                
                if not success:
                    self.logger.info("[ScanEngine] No valid creds or login failed. Trying aggressive entry...")
                    success = await self.crawler.auth_handler.aggressive_entry(page)
                
                if success:
                    self.logger.info("[ScanEngine] Login successful! Session captured.")
                else:
                    self.logger.warning("[ScanEngine] Could not authenticate. Discovery will be limited.")
                
                await page.close()

            # Crawling
            self.logger.info(f"[ScanEngine] Starting Discovery on {self.target}...")
            crawled_targets = await self.crawler.crawl(self.target)
            print(crawled_targets)

            # [MODIFIED] ทำความสะอาด URL ก่อนส่งกลับ
            cleaned_urls = [normalize_url(t["url"]) for t in crawled_targets]
            self.logger.info(f"[ScanEngine] Discovery finished. Unique targets found: {len(crawled_targets)}")

            # 3. Session Persistence (สำคัญมาก!)
            # ดึงข้อมูลจาก AuthHandler เพื่อส่งต่อให้ Scanner

            auth_info = {
                "cookies": self.crawler.auth_handler.cookies,
                "auth_storage": getattr(self.crawler.auth_handler, 'auth_storage', None)
            }

            if auth_info["cookies"]:
                self.logger.info("[Orchestrator] 🍪 Session captured. Syncing with scanners...")
                # อัปเดต Requester (สำหรับ HTTP Scanners)
                formatted_cookies = {c['name']: c['value'] for c in auth_info["cookies"]}
                self.requester.set_cookies(formatted_cookies)
                
                # อัปเดต Scanners (สำหรับ Verifiers ที่ใช้ Browser)
                self.reflected_scanner.verifier.auth_data = auth_info
                # DOM Scanner มักจะใช้ context ใหม่ จึงต้องถือ auth_info ไว้
                self.dom_scanner.auth_info = auth_info 

            # 4. Attack Phase
            results = []
            if not crawled_targets:
                self.logger.warning("[ScanEngine] No targets found during crawling. Scanning entry point only.")
                # Fallback: อย่างน้อยให้สแกนหน้าแรกที่ผู้ใช้ส่งมา
                crawled_targets = [{"url": self.target, "method": "GET", "params": {}, "content_type": "form"}]

            if self.attack_type == "sql_injection":
                results = self._run_sqli_scan(crawled_targets)
            elif self.attack_type == "XSS":
                results = self._run_xss_scan(crawled_targets)
            else:
                self.logger.warning(f"[ScanEngine] Unknown attack type: {self.attack_type}")

            return self._build_response(
                "found" if results else "not found",
                findings=results,
                target_count=len(crawled_targets),
                crawler_urls=cleaned_urls
            )

        except Exception as e:
            self.logger.error(f"❌ Critical Error: {str(e)}")
            return self._build_response("failed", error=str(e))
        
        finally:
            self._cleanup_logger()

    def _build_response(self, status, findings=[], target_count=0, error=None, crawler_urls=[]):
        """Helper สำหรับสร้างโครงสร้างข้อมูลขากลับ"""
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
        if hasattr(self, 'capture_handler'):
            self.logger.removeHandler(self.capture_handler)
            self.capture_handler.close()

    def _run_xss_scan(self, targets: list):
        findings = []
        for t in targets:
            url, method, params, c_type = t["url"], t["method"], t.get("params", {}), t.get("content_type", "form")
            self.logger.info(f"--- XSS Scan on: {url} ({method}) ---")

            is_api = any(x in url.lower() for x in ["/rest/", "/api/", ".json"])
            
            # Run Reflected
            findings.extend(self.reflected_scanner.scan(url, params, method, c_type))
            # Run DOM (สังเกตว่าส่ง auth_info เข้าไปเพื่อให้ Verifier ใช้ได้)
            if not is_api:
                self.dom_scanner.auth_info = {
                    "cookies": self.crawler.auth_handler.cookies,
                    "auth_storage": self.crawler.auth_handler.auth_token
                }
                findings.extend(self.dom_scanner.scan(url, params, method))
        return findings

    def _run_sqli_scan(self, targets: list):
        findings = []
        for t in targets:
            url, method, params, c_type = t["url"], t["method"], t.get("params", {}), t.get("content_type", "form")
            self.logger.info(f"--- SQLi Scan on: {url} ({method}) ---")
            findings.extend(self.sqli_scanner.scan(url, params, method, c_type))
        return findings