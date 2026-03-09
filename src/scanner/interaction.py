from playwright.async_api import Page
from src.core.logger import setup_logger

class InteractionEngine:
    def __init__(self, logger):
        self.logger = logger or setup_logger("Crawler")

    async def trigger_smart_interaction(self, page: Page):
        self.logger.info("    [..] Triggering smart interactions...")
        
        # 1. Fill visible inputs
        inputs = await page.locator("input:visible, textarea:visible").all()
        for i, inp in enumerate(inputs[:10]):
            try:
                i_type = await inp.get_attribute("type") or ""
                if i_type in ["password", "submit", "button"]: continue
                await inp.fill(f"test_data_{i}")
            except: continue

        # 2. Click buttons (Avoid Logout)
        buttons = await page.locator("button:visible, [role='button']:visible").all()
        for btn in buttons[:5]:
            try:
                text = (await btn.inner_text()).lower()
                # Blacklist keywords สำหรับปุ่มที่ห้ามกด
                if any(x in text for x in ["logout", "signout", "exit", "ออกจากระบบ", "delete"]): 
                    continue
                
                await btn.click(timeout=1000)
                await page.wait_for_timeout(500) # รอ network ทำงานสั้นๆ
            except: continue