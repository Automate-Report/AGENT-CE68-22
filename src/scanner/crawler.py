import time
from playwright.sync_api import sync_playwright, Page
from src.scanner.deduplicator import Deduplicator
from src.core.logger import setup_logger

from urllib.parse import urlparse, urljoin

class Target:
    def __init__(self, url, method, content_type, params):
        self.url = url
        self.method = method
        self.content_type = content_type
        self.params = params

class Crawler:
    def __init__(self, logger = None):
        self.deduplicator = Deduplicator()
        self.logger = logger or setup_logger("Crawler")
        self.collected_targets = []  # เก็บ {url, params}
        self.visited_urls = set()

    def crawl(self, start_url: str, max_depth: int = 2):
        """
        Main Entry Point: ควบคุม Loop การ Crawl พร้อม Debug Log ละเอียด
        """
        self.logger.info(f"[Crawler] Starting Crawl on: {start_url} (Depth: {max_depth})")
        
        base_domain = urlparse(start_url).netloc
        self.logger.debug(f"    [DEBUG] Scope set to domain: {base_domain}")
        
        queue = [(start_url, 0)]
        visited_urls = set()

        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)
            context = browser.new_context(ignore_https_errors=True)
            page = context.new_page()

            while queue:
                # Debug: ดูสถานะคิว
                self.logger.debug(f"    [DEBUG] Queue Size: {len(queue)} | Visited: {len(visited_urls)}")
                
                current_url, current_depth = queue.pop(0) 
                
                # 1. Debug: เช็คเงื่อนไขการ Skip
                if current_url in visited_urls:
                    # self.logger.debug(f"    [DEBUG] Skipping {current_url} (Already visited)")
                    continue
                
                if current_depth > max_depth:
                    self.logger.debug(f"    [DEBUG] Skipping {current_url} (Max depth {max_depth} reached)")
                    continue
                
                visited_urls.add(current_url)
                
                try:
                    # Debug: เริ่ม Process หน้า
                    # self.logger.info(f"    [>] Crawling: {current_url} (Depth: {current_depth})")
                    start_time = time.time()
                    
                    found_params = self._process_page(page, current_url)
                    
                    # Debug: ดูเวลาที่ใช้ต่อหน้า
                    elapsed = time.time() - start_time
                    self.logger.debug(f"    [DEBUG] Processed in {elapsed:.2f}s | Found params: {len(found_params)}")
                    
                    self._save_target(current_url, found_params)

                    # 3. หา Link ไปต่อ
                    if current_depth < max_depth:
                        new_links = self._discover_links(page, current_url, base_domain)
                        
                        # Debug: ดูจำนวน Link ที่เจอ
                        added_count = 0
                        for link in new_links:
                            if link not in visited_urls:
                                queue.append((link, current_depth + 1))
                                added_count += 1
                        
                        self.logger.debug(f"    [DEBUG] Discovered {len(new_links)} links -> Added {added_count} new to queue.")
                                
                except Exception as e:
                    self.logger.error(f"[Crawler][-] Error processing {current_url}: {e}")

            browser.close()
            
        return self.collected_targets

    # =========================================================================
    # Helper Functions (แยกย่อยการทำงาน)
    # =========================================================================

    def _process_page(self, page: Page, url: str) -> dict:
        self.logger.info(f"    [>] Crawling: {url}")
        
        try:
            # [FIX 1] เปลี่ยนจาก networkidle เป็น domcontentloaded เพื่อแก้ Timeout
            # เพราะหน้าเว็บ XSS Test บางหน้ามัน Redirect วน หรือโหลดไม่หยุด
            page.goto(url, wait_until="domcontentloaded", timeout=10000)
        except Exception as e:
            # ถ้า Timeout หรือ Error ให้ถือว่าโหลดเสร็จเท่าที่ได้ แล้วทำงานต่อ
            self.logger.warning(f"    [!] Page load warning: {e}")

        all_params = {}
        
        # A. ดึงจาก URL Query String
        all_params.update(self._extract_url_params(page.url))
        
        # B. ดึงจาก HTML Forms/Inputs
        all_params.update(self._extract_form_params(page))
        
        return all_params

    def _extract_url_params(self, current_url: str) -> dict:
        """
        หน้าที่: แกะ Query String (?id=1)
        """
        params = {}
        if "?" in current_url:
            try:
                _, query = current_url.split("?", 1)
                # แปลง string เป็น dict
                for pair in query.split("&"):
                    if "=" in pair:
                        key, val = pair.split("=", 1)
                        params[key] = val
            except:
                pass
        return params

    def _extract_form_params(self, page: Page) -> dict:
        """
        หน้าที่: แกะ Input บนหน้าเว็บ พร้อมตั้งชื่อ Anonymous
        """
        params = {}
        # กวาด Input ทุกตัวที่มองเห็น
        elements = page.query_selector_all("input:not([type='hidden']), textarea, select")
        
        for i, el in enumerate(elements):
            try:
                p_name = el.get_attribute("name")
                if not p_name:
                    p_name = el.get_attribute("id")
                
                # ถ้าไม่มีทั้ง Name และ ID ให้ตั้งชื่อสมมติ
                if not p_name:
                    p_name = f"anonymous_input_{i+1}"
                
                params[p_name] = "test_value"
            except:
                continue
        return params

    def _discover_links(self, page: Page, current_url: str, allowed_domain: str) -> set:
        """
        หน้าที่: หา <a> tags เพื่อไปต่อ (Link Discovery)
        """
        links_found = set()
        elements = page.query_selector_all("a[href]")
        
        for el in elements:
            try:
                href = el.get_attribute("href")
                if not href or href.startswith(("#", "javascript:", "mailto:")):
                    continue
                
                # แปลง Relative path (/login) เป็น Full URL (http://site.com/login)
                full_url = urljoin(current_url, href)
                
                # ลบ Query Param ออกเพื่อให้ได้ Base URL ที่จะไป Crawl ต่อ
                # (เราจะไป Crawl หน้าใหม่ ไม่ใช่หน้าเดิมที่เปลี่ยน param)
                clean_url = full_url.split("?")[0].split("#")[0]
                
                # Scope Check: ห้ามหลุดไปเว็บอื่น (เช่น facebook, google)
                if urlparse(clean_url).netloc == allowed_domain:
                    links_found.add(clean_url)
                    
            except:
                continue
                
        return links_found

    def _save_target(self, url: str, params: dict):
        """
        หน้าที่: บันทึกผลลัพธ์ลง List (และกันซ้ำ)
        """
        # สร้าง Signature กันซ้ำ (URL + Param Keys)
        base_url = url.split("?")[0]
        sig = f"{base_url}|{sorted(params.keys())}"
        
        if not self.deduplicator.is_seen(sig):
            self.deduplicator.add(sig)
            self.collected_targets.append({
                "url": base_url,
                "params": params
            })
            self.logger.info(f"    [+] Found Params: {params}")