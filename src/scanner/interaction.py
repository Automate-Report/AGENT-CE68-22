from playwright.async_api import Page
from src.core.logger import setup_logger

class InteractionEngine:
    def __init__(self, logger):
        self.logger = logger or setup_logger("Crawler")

    async def trigger_smart_interaction(self, page: Page):
        # ค้นหาปุ่มที่น่าจะเป็นปุ่มเมนูหรือปุ่มเปิด Sidebar
        buttons = await page.locator("button:visible, [role='button']:visible").all()
        
        for btn in buttons[:10]:
            try:
                text = (await btn.inner_text()).lower()
                # ถ้ามีคำพวกนี้ ห้ามกดบ่อยๆ เพราะจะทำให้ Sidebar เด้งไปมา
                if any(x in text for x in ["menu", "navigation", "side", "hamburger"]):
                    continue
                
                # ถ้าปุ่มเปิด Sidebar อยู่แล้ว ให้ข้ามไป
                is_expanded = await btn.get_attribute("aria-expanded")
                if is_expanded == "true":
                    continue

                await btn.click(timeout=1500)
                await page.wait_for_timeout(800)
            except:
                continue