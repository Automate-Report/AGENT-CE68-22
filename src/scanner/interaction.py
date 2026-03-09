from playwright.async_api import Page
from src.core.logger import setup_logger

class InteractionEngine:
    def __init__(self, logger):
        self.logger = logger or setup_logger("Crawler")

    async def trigger_smart_interaction(self, page: Page):
        # 1. กรอกข้อมูลทุกช่องที่เจอด้วย "XSS Payload" เบื้องต้น (ตามที่คุณต้องการ)
        inputs = await page.locator("input:visible, textarea:visible").all()
        for inp in inputs:
            try:
                # ข้ามปุ่มและช่องที่ถูกล็อก
                if await inp.is_editable():
                    await inp.fill("<script>alert('pentest')</script>")
            except: continue

        # 2. กดปุ่ม (ข้ามปุ่ม Logout)
        buttons = await page.locator("button:visible, a.mat-menu-item").all()
        for btn in buttons[:15]: # เพิ่มจำนวนการคลิกให้มากขึ้น
            try:
                inner_html = await btn.inner_html()
                if any(x in inner_html.lower() for x in ["logout", "signout", "exit"]): continue
                
                await btn.click(timeout=2000)
                await page.wait_for_timeout(1000) # รอให้เกิด API Call
            except: continue