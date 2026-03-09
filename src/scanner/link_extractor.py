from playwright.async_api import Page
from urllib.parse import urljoin, urlparse

class LinkExtractor:
    def __init__(self, base_domain: str, blacklisted_domains: list):
        self.base_domain = base_domain
        self.blacklist = blacklisted_domains

    async def extract(self, page: Page, current_url: str) -> set:
        # self.logger.info("    [..] Extracting universal links...")
        
        # ใช้ Script ที่ดึงทุก Attribute ที่เกี่ยวข้องกับ Navigation
        script = """() => {
            const attrs = ['href', 'routerlink', 'ng-reflect-router-link', 'data-url', 'to', 'navlink'];
            const discovered = new Set();
            document.querySelectorAll('*').forEach(el => {
                attrs.forEach(attr => {
                    const val = el.getAttribute(attr);
                    // เก็บเฉพาะ path ที่ไม่ใช่ลิงก์ภายนอกทื่อๆ หรือ javascript
                    if (val && val.length > 1 && !val.startsWith('http') && !val.startsWith('javascript:')) {
                        discovered.add(val);
                    }
                });
            });
            return Array.from(discovered);
        }"""
        
        raw_paths = await page.evaluate(script)
        base_parsed = urlparse(current_url)
        links_found = set()

        for path in raw_paths:
            # แปลง path (เช่น /search หรือ search) ให้เป็น URL ที่สมบูรณ์
            # โดยยังคงโครงสร้าง # สำหรับ SPA
            if not path.startswith("#"):
                full_url = f"{base_parsed.scheme}://{base_parsed.netloc}/#/{path.lstrip('/')}"
            else:
                full_url = urljoin(current_url, path)
            
            links_found.add(full_url.split('?')[0].rstrip('/'))
                    
        return links_found