# security-worker/main.py
import requests

from src.scanner.crawler import Crawler
from src.core.logger import setup_logger

from src.exploits.xss.scanner import XSSScanner
from src.exploits.xss.dom_scanner import DOMScanner
from src.exploits.sqli.scanner import SQLiScanner

def test_xss():
    logger = setup_logger("Worker")

    reflected_scanner = XSSScanner()
    crawler = Crawler()
    dom_scanner = DOMScanner()
    sqli_scanner = SQLiScanner()

    logger.info("[*] Crawler is running...")
    target_url = "http://testphp.vulnweb.com/search.php"
    # https://public-firing-range.appspot.com/address/index.html
    # http://testphp.vulnweb.com/search.php
    # https://xss-game.appspot.com/level2/frame
    # http://localhost:4040/#/search

    crawled_targets = crawler.crawl(target_url)
    logger.info(f"[*] Found {len(crawled_targets)} targets. Starting Scans...")
    url_attacked = []
    
    for t in crawled_targets:
        url = t['url']
        params = t.get('params', {}) # จะให้ใส่มาได้ไหม

        logger.info(f"--- Analyzing: {url} ---")
        
        logger.info("[1] Running Reflected Scan...")
        findings_reflected = reflected_scanner.scan(url, params)
        if findings_reflected:
            logger.info(f"[!!!] VULNERABILITY FOUND at {url}")
            url_attacked.append(url)
            for f in findings_reflected:
                # logger.info(f"   -> Payload: {f['payload']}")
                # logger.info(f"   -> Context: {f['context']}")
                # logger.info(f"   -> Screenshot: {f['screenshot']}")
                # if f.get('confirmed'):
                #     logger.info(f"   -> Status: CONFIRMED (Alert Popped) 🚨")
                try:
                    # ส่ง JSON ไปหา Backend
                    res = requests.post("http://localhost:8000/pentest-logs/", json=f)
                    if res.status_code == 201:
                        print("[+] Report sent to Backend successfully!")
                    else:
                        print(f"[-] Failed to send report: {res.text}")
                except Exception as e:
                    print(f"[-] Backend Connection Error: {e}")
        else:
            logger.info(f"[-] Clean: {url}")
        
        logger.info("[2] Running DOM Scan...")
        findings_dom = dom_scanner.scan(url, params)
        if findings_dom:
            logger.info(f"    🚨 DOM XSS Found!")
            url_attacked.append(url)
            for f in findings_dom:
            #     # logger.info(f"   -> Payload: {f['payload']}")
            #     # logger.info(f"   -> Context: {f['context']}")
            #     # logger.info(f"   -> Screenshot: {f['screenshot']}")
            #     # if f.get('confirmed'):
            #     #     logger.info(f"   -> Status: CONFIRMED (Alert Popped) 🚨")
            #     print(f)
                try:
                    # ส่ง JSON ไปหา Backend
                    res = requests.post("http://localhost:8000/pentest-logs/", json=f)
                    if res.status_code == 201:
                        print("[+] Report sent to Backend successfully!")
                    else:
                        print(f"[-] Failed to send report: {res.text}")
                except Exception as e:
                    print(f"[-] Backend Connection Error: {e}")
        else:
            logger.info(f"[-] Clean: {url}")
        logger.info("[2] Running SQLi Scan...")
        findings_sqli = sqli_scanner.scan(url, params)
        if findings_sqli:
            logger.info(f"[!!!] VULNERABILITY FOUND at {url}")
            url_attacked.append(url)
            for f in findings_sqli:
            #     # logger.info(f"   -> Payload: {f['payload']}")
            #     # logger.info(f"   -> Type: {f['type']}")
            #     # logger.info(f"   -> Screenshot: {f['screenshot']}")
            #     # if f.get('confirmed'):
            #     #     logger.info(f"   -> Status: CONFIRMED (Alert Popped) 🚨")
            #     print(f)
                try:
                    # ส่ง JSON ไปหา Backend
                    res = requests.post("http://localhost:8000/pentest-logs/", json=f)
                    if res.status_code == 201:
                        print("[+] Report sent to Backend successfully!")
                    else:
                        print(f"[-] Failed to send report: {res.text}")
                except Exception as e:
                    print(f"[-] Backend Connection Error: {e}")
        else:
            logger.info(f"[-] Clean: {url}")

    # print(findings_sqli)
    return True

def test_sqli():
    sqli_scanner = SQLiScanner()
    results = sqli_scanner.scan("http://testphp.vulnweb.com/listproducts.php", {"cat": "1"})

    return results

