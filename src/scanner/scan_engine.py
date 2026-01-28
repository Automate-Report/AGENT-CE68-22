from src.scanner.crawler import Crawler
from src.exploits.xss.scanner import XSSScanner
from src.exploits.xss.dom_scanner import DOMScanner
from src.exploits.sqli.scanner import SQLiScanner
from src.core.logger import setup_logger
from src.networking.requester import Requester

class ScanOrchestrator:
    def __init__(self, job_data: dict):
        self.job_id = job_data.get("id")
        self.target = job_data.get("target_url")
        self.attack_type = job_data.get("attack_type")
        self.cred = job_data.get("credentials")

        self.logger = setup_logger("ScanEngine")
        # Init Tools
        self.requester = Requester()
        self.crawler = Crawler()
        self.reflected_scanner = XSSScanner() 
        self.dom_scanner = DOMScanner()
        self.sqli_scanner = SQLiScanner()

    def run_workflow(self):
        self.logger.info(f"[Job {self.job_id}] Starting Discovery Phase...")

        crawled_targets = self.crawler.crawl(self.target)
        self.logger.info(f"[*] [Job {self.job_id}] Discovery finished. Unique targets: {len(crawled_targets)}")

        results = []

        if self.attack_type == "sql_injection":
            results = self._run_xss_scan(crawled_targets)
        elif self.attack_type == "xss":
            results = self._run_sqli_scan(crawled_targets)
        else:
            self.logger.warning("Unknown attack type: {self.attack_type}")

        return {
            "job_id": self.job_id,
            "status": "completed",
            "findings": results,
            "target_count": len(crawled_targets)
        }
    
    def _run_xss_scan(self, targets):
        findings = []
        for t in targets:
            url = t["url"]
            params = dict(t).get('params', {})

            self.logger.info(f"--- Analyzing: {url} ---")

            self.logger.info(f"[Job {self.job_id}] Running Reflected Scan...")
            findings_reflected = self.reflected_scanner.scan(url, params)

            self.logger.info(f"[Job {self.job_id}] Running DOM Scan...")
            findings_dom = self.dom_scanner.scan(url, params)

            
            findings.extend(findings_reflected)
            findings.extend(findings_dom)

        return findings
        
    def _run_sqli_scan(self, targets):
        findings = []
        for t in targets:
            url = t["url"]
            params = dict(t).get('params', {})
            self.logger.info(f"--- Analyzing: {url} ---")
            self.logger.info(f"[Job {self.job_id}] Running SQLi Scan...")
            findings_sqli = self.sqli_scanner.scan(url, params)
            findings.extend(findings_sqli)
        return findings
