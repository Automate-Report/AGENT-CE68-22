from playwright.async_api import Page
from urllib.parse import urljoin, urlparse

class LinkExtractor:
    def __init__(self, base_domain: str, blacklisted_domains: list):
        self.base_domain = base_domain
        self.blacklist = blacklisted_domains

    async def extract(self, page: Page, current_url: str) -> set:
        links_found = set()
        
        # ดึงทุกลิงก์และทุกอย่างที่ดูเหมือนจะคลิกแล้วเปลี่ยนหน้าได้
        script = """() => {
            const results = [];
            // 1. มาตรฐาน <a>
            document.querySelectorAll('a[href]').forEach(el => results.push(el.getAttribute('href')));
            // 2. SPA Specific (Angular/Vue/React)
            document.querySelectorAll('[routerlink], [navlink], [ng-reflect-router-link]').forEach(el => {
                results.push(el.getAttribute('routerlink') || el.getAttribute('ng-reflect-router-link'));
            });
            return results;
        }"""
        
        raw_paths = await page.evaluate(script)
        base_parsed = urlparse(current_url)

        for path in raw_paths:
            if not path or path.startswith(("javascript:", "mailto:", "tel:")): continue
            
            # ถ้าเป็น SPA Route (เช่น /search หรือ search) ให้แปลงเป็น /#/search
            if not path.startswith(("http", "#")):
                full_url = f"{base_parsed.scheme}://{base_parsed.netloc}/#/{path.lstrip('/')}"
            else:
                full_url = urljoin(current_url, path)

            # กรองเอาเฉพาะ Domain เดียวกัน
            parsed_full = urlparse(full_url)
            if parsed_full.netloc == self.base_domain:
                # เก็บแบบ Clean URL (ตัดส่วนเกินท้ายออก)
                links_found.add(full_url.split('?')[0].rstrip('/'))
                    
        return links_found