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
        
        for i, el in enumerate(elements):
            try:
                # ข้ามพวกปุ่มกด
                e_type = await el.get_attribute("type") or "text"
                if e_type in ["submit", "button", "reset", "image"]:
                    continue

                # ลำดับความสำคัญในการหาชื่อพารามิเตอร์
                name = await el.get_attribute("name")
                placeholder = await el.get_attribute("placeholder")
                eid = await el.get_attribute("id") or ""
                
                # จัดการกับ Dynamic IDs (เช่น mat-input-0)
                if not name and not placeholder:
                    if "mat-input-" in eid or "input-" in eid:
                        key = "dynamic_input_field"
                    else:
                        key = eid or f"field_{i}"
                else:
                    key = name or placeholder

                # ทำความสะอาด Key
                key = re.sub(r'[^a-zA-Z0-9_]', '_', key).lower()
                
                # เก็บค่าเป็นโครงสร้าง dict (เตรียมไว้ใส่ default value ในอนาคต)
                params[key] = ""
            except Exception as e:
                continue
                
        return params