from playwright.async_api import Page
import re

class ParameterExtractor:
    def __init__(self, logger):
        self.logger = logger

    async def extract_from_dom(self, page: Page) -> dict:
        params = {}
        # ดึง input ที่มองเห็นได้ และไม่ใช่ปุ่ม
        selector = "input:visible, textarea:visible, select:visible"
        elements = await page.locator(selector).all()
        attrs_to_check = ["name", "placeholder", "id", "formcontrolname", "aria-label"]
        
        for i, el in enumerate(elements):
            try:
                key = None
                for attr in attrs_to_check:
                    val = await el.get_attribute(attr)
                    if val:
                        key = val
                        break
                
                if not key:
                    key = f"field_{i}"
                    
                key = re.sub(r'[^a-zA-Z0-9_]', '_', key).lower()
                params[key] = ""
            except: continue
                
        return params