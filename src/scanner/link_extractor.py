from playwright.async_api import Page
from urllib.parse import urljoin, urlparse

class LinkExtractor:
    def __init__(self, base_domain: str, blacklisted_domains: list):
        self.base_domain = base_domain
        self.blacklist = blacklisted_domains

    async def extract(self, page: Page, current_url: str) -> set:
        links_found = set()
        
        # 1. ดึงจาก <a> tags (Standard HTML)
        hrefs = await page.evaluate("""() => 
            Array.from(document.querySelectorAll('a[href]'))
                 .map(a => a.getAttribute('href'))
        """)
        
        # 2. ดึงจาก Router Links (SPA เช่น Angular/Vue)
        router_links = await page.evaluate("""() => 
            Array.from(document.querySelectorAll('[routerlink], [navlink]'))
                 .map(el => el.getAttribute('routerlink') || el.getAttribute('navlink'))
        """)

        all_paths = set(hrefs + router_links)

        for path in all_paths:
            if not path or path.startswith(("javascript:", "mailto:", "tel:", "#")):
                continue
                
            full_url = urljoin(current_url, path)
            parsed = urlparse(full_url)
            
            # กรองให้เอาเฉพาะ Domain เดียวกันและไม่อยู่ใน Blacklist
            if parsed.netloc == self.base_domain:
                if not any(d in full_url for d in self.blacklist):
                    # ลบ fragment (#) ออกเพื่อให้ URL สะอาด
                    links_found.add(full_url.split('#')[0].rstrip('/'))
                    
        return links_found