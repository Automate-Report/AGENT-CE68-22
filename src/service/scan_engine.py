from core.crawler import Crawler
from modules.xss.scanner import XSSScanner
from modules.xss.dom_scanner import DOMScanner
from core.logger import setup_logger
from core.requester import Requester

class ScanEngine:
    def __init__(self):
        self.logger = setup_logger("ScanEngine")
        # Init Tools
        self.requester = Requester()
        self.crawler = Crawler()
        self.reflected_scanner = XSSScanner(self.requester) # ส่ง requester เข้าไป
        self.dom_scanner = DOMScanner()

    def run(self, target_url):
        """
        Workflow หลัก:
        1. Crawl หา URL/Params
        2. Loop Scan (Reflected)
        3. Loop Scan (DOM/RPA)
        4. รวมผลลัพธ์
        """
        all_findings = []
        self.logger.info(f"=== Starting Engine on {target_url} ===")

        # --- STEP 1: CRAWLING ---
        self.logger.info("[1/3] Crawling target...")
        targets = self.crawler.crawl(target_url, max_depth=2)
        self.logger.info(f"      > Found {len(targets)} potential injection points.")

        # --- STEP 2: SCANNING LOOP ---
        for i, t in enumerate(targets):
            url = t['url']
            params = t['params'] # Dict
            
            self.logger.info(f"--- Processing [{i+1}/{len(targets)}]: {url} ---")

            # A. Reflected Scan (Requests)
            # สแกนเฉพาะถ้ามี Params (ถ้าไม่มี params reflected มักไม่เกิด)
            if params:
                findings_ref = self.reflected_scanner.scan(url, params)
                if findings_ref:
                    all_findings.extend(findings_ref)

            # B. DOM Scan (Playwright/RPA)
            # ส่งให้ DOM Scanner (ซึ่งมี Logic Fuzzing URL ในตัวแล้ว แม้ไม่มี Params ก็ทำงานได้)
            findings_dom = self.dom_scanner.scan(url, params)
            if findings_dom:
                all_findings.extend(findings_dom)

        self.logger.info(f"=== Scan Finished. Total Findings: {len(all_findings)} ===")
        return all_findings