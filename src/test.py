import requests
from src.scanner.crawler import Crawler
from src.core.logger import setup_logger

from src.exploits.xss.scanner import XSSScanner
from src.exploits.xss.dom_scanner import DOMScanner
from src.exploits.sqli.scanner import SQLiScanner

def send_to_backend(data, logger):
    """Helper function สำหรับส่งผลลัพธ์ไปที่ Backend"""
    try:
        backend_url = "https://ce-backend.onikla.org/"
        res = requests.post(backend_url, json=data)
        if res.status_code == 201:
            logger.info("[+] Report sent to Backend successfully!")
        else:
            logger.error(f"[-] Failed to send report: {res.text}")
    except Exception as e:
        logger.error(f"[-] Backend Connection Error: {e}")

def run_security_test():
    logger = setup_logger("Worker")
    
    # Initialize Scanners
    crawler = Crawler()
    reflected_scanner = XSSScanner()
    dom_scanner = DOMScanner()
    sqli_scanner = SQLiScanner()

    # Target URL ที่ต้องการทดสอบ
    target_url = "https://ce-backend.onikla.org/" 
    
    logger.info(f"[*] Starting Discovery on: {target_url}")
    
    # 1. Crawling Phase
    # คืนค่าเป็น List ของออบเจกต์ Target (ที่มี url, method, params, content_type)
    crawled_targets = crawler.crawl(target_url, max_depth=1)
    
    logger.info(f"[*] Discovery complete. Found {len(crawled_targets)} potential targets.")
    
    for target in crawled_targets:
        # ดึงข้อมูลจากออบเจกต์ Target
        url = target.url
        method = target.method
        params = target.params
        c_type = target.content_type

        logger.info(f"\n--- 🛡️ Analyzing: {method} {url} ---")
        
        # [1] Reflected XSS Scan (รองรับ Multi-Method)
        logger.info(f"[1] Running Reflected Scan ({method})...")
        findings_reflected = reflected_scanner.scan(url, params, method, c_type)
        if findings_reflected:
            logger.info(f"🚨 [!!!] Reflected XSS FOUND at {url}")
            for f in findings_reflected:
                send_to_backend(f, logger)
        else:
            logger.info(f"[-] Reflected XSS: Clean")

        # [2] DOM XSS Scan
        # หมายเหตุ: DOM XSS ส่วนใหญ่เน้นที่การ Render หน้าเว็บ (ใช้ GET เป็นหลัก)
        if method == "GET":
            logger.info("[2] Running DOM Scan...")
            findings_dom = dom_scanner.scan(url, params)
            if findings_dom:
                logger.info(f"🚨 [!!!] DOM XSS FOUND at {url}")
                for f in findings_dom:
                    send_to_backend(f, logger)
            else:
                logger.info(f"[-] DOM XSS: Clean")

        # [3] SQL Injection Scan
        logger.info(f"[3] Running SQLi Scan ({method})...")
        # หาก SQLiScanner ของคุณยังไม่รองรับ method ให้ส่งแค่ url, params ไปก่อน
        findings_sqli = sqli_scanner.scan(url, params) 
        if findings_sqli:
            logger.info(f"🚨 [!!!] SQLi FOUND at {url}")
            for f in findings_sqli:
                send_to_backend(f, logger)
        else:
            logger.info(f"[-] SQLi: Clean")

    logger.info("\n[*] --- All scans completed ---")

if __name__ == "__main__":
    run_security_test()