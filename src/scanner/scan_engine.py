import io
import logging

from src.scanner.crawler import Crawler
from src.exploits.xss.scanner import XSSScanner
from src.exploits.xss.dom_scanner import DOMScanner
from src.exploits.sqli.scanner import SQLiScanner
from src.core.logger import setup_logger
from src.networking.requester import Requester

class ScanOrchestrator:
    def __init__(self, job_data: dict):
        print(f"DEBUG: ScanOrchestrator received: {job_data}")
        self.job_id = job_data.get("job_id")
        self.target = job_data.get("target_url")
        self.attack_type = job_data.get("attack_type")
        # self.cred = job_data.get("credentials")

        self.logger = setup_logger(f"ScanEngine-{self.job_id}")
        # Init Tools
        self.requester = Requester(logger=self.logger)
        self.crawler = Crawler(logger=self.logger)
        self.reflected_scanner = XSSScanner(logger=self.logger) 
        self.dom_scanner = DOMScanner(logger=self.logger)
        self.sqli_scanner = SQLiScanner(logger=self.logger)

        # Logger
        self.log_capture = io.StringIO()
        self.capture_handler = logging.StreamHandler(self.log_capture)

        formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', '%H:%M:%S')
        self.capture_handler.setFormatter(formatter)
        
        # เพิ่ม Handler ตัวนี้เข้าไปใน logger (ตอนนี้ logger จะพ่นออก 2 ทาง: จอภาพ + ตัวแปร)
        self.logger.addHandler(self.capture_handler)

    def _get_captured_logs(self):
        """ดึง log ทั้งหมดที่สะสมไว้ใน StringIO"""
        self.capture_handler.flush() # ดันข้อมูลที่ค้างอยู่ลง stream
        return self.log_capture.getvalue()

    def run_workflow(self):
        try:
            self.logger.info(f"[ScanEngine][Job {self.job_id}] Starting Discovery Phase...")

            crawled_targets = self.crawler.crawl(self.target)
            self.logger.info(f"[ScanEngine][Job {self.job_id}] Discovery finished. Unique targets: {len(crawled_targets)}")

            results = []

            if self.attack_type == "sql_injection":
                results = self._run_sqli_scan(crawled_targets)
            elif self.attack_type == "xss":
                results = self._run_xss_scan(crawled_targets)
            else:
                self.logger.warning(f"[ScanEngine] Unknown attack type: {self.attack_type}")

            status = "found" if results else "not found"

            return {
                "job_id": int(self.job_id),
                "status": status,
                "findings": results,
                "target_count": len(crawled_targets),
                "error_log": None,
                "crawler_urls": crawled_targets,
                "execution_logs": self._get_captured_logs()
            }
        except Exception as e:

            error_msg = str(e)

            self.logger.error(f"❌ Critical Error: {error_msg}")

            return {
                "job_id": int(self.job_id),
                "status": "failed",
                "findings": [],
                "target_count": 0,
                "error_log": error_msg,
                "crawler_urls": [],
                "execution_logs": self._get_captured_logs()
            }
        
        finally:
            # การันตีว่า Handler จะถูกลบออกเสมอ ไม่ว่ารันผ่านหรือพัง
            # เพื่อป้องกัน memory leak หรือ log พ่นซ้ำในอนาคต
            if hasattr(self, 'capture_handler'):
                self.logger.removeHandler(self.capture_handler)
    
    def _run_xss_scan(self, targets):
        findings = []
        for t in targets:
            url = t["url"]
            params = dict(t).get('params', {})

            self.logger.info(f"[ScanEngine] --- Analyzing: {url} ---")

            self.logger.info(f"[ScanEngine][Job {self.job_id}] Running Reflected Scan...")
            findings_reflected = self.reflected_scanner.scan(url, params)

            self.logger.info(f"[ScanEngine][Job {self.job_id}] Running DOM Scan...")
            findings_dom = self.dom_scanner.scan(url, params)

            
            findings.extend(findings_reflected)
            findings.extend(findings_dom)

        return findings
        
    def _run_sqli_scan(self, targets):
        findings = []
        for t in targets:
            url = t["url"]
            params = dict(t).get('params', {})
            self.logger.info(f"[ScanEngine] --- Analyzing: {url} ---")
            self.logger.info(f"[ScanEngine][Job {self.job_id}] Running SQLi Scan...")
            findings_sqli = self.sqli_scanner.scan(url, params)
            findings.extend(findings_sqli)
        return findings
