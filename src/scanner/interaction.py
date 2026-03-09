from playwright.async_api import Page
from src.core.logger import setup_logger

class InteractionEngine:
    def __init__(self, logger):
        self.logger = logger or setup_logger("Crawler")

    # ใน InteractionEngine.py
    async def trigger_smart_interaction(self, page: Page):
        self.logger.info("    [..] Executing behavioral exploration...")

        # 1. Clear Obstacles (Generic Modal/Banner Closer)
        # มองหาปุ่มที่มีคำจำพวก "ปิด" หรือ "ยอมรับ"
        obstacles = page.locator("button:has-text('Close'), button:has-text('Dismiss'), button:has-text('Accept'), button:has-text('Got it')")
        try:
            for i in range(await obstacles.count()):
                if await obstacles.nth(i).is_visible():
                    await obstacles.nth(i).click(timeout=1000)
        except: pass

        # 2. Universal Scroll (เพื่อกระตุ้น Lazy Loading API)
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(2000)

        # 3. Form Interaction (ลองป้อนข้อมูลทดสอบและกด Enter)
        inputs = await page.locator("input:visible, textarea:visible").all()
        for i, inp in enumerate(inputs[:5]): # จำกัดแค่ 5 ช่องเพื่อไม่ให้เสียเวลาเกินไป
            try:
                if await inp.is_editable():
                    # ป้อนข้อมูลทดสอบ (ใช้คำที่น่าจะกระตุ้น Search ได้ เช่น 'apple')
                    test_value = f"test_query_{i}"
                    await inp.fill(test_value)
                    
                    # จำลองการกด Enter เพื่อส่งข้อมูล (Submit via Keyboard)
                    await inp.press("Enter")
                    self.logger.info(f"    [!] Injected & Pressed Enter on input {i}")
                    
                    # รอ Network ทำงานสั้นๆ เพื่อให้ Interceptor ดักจับ API ทัน
                    await page.wait_for_timeout(1500)
                    # เคลียร์ Modal ที่อาจเด้งขึ้นมาหลังกด Enter
                    await page.keyboard.press("Escape")
            except: continue

        # 4. Generic Clicking (ลองคลิกสิ่งที่น่าจะคลิกได้)
        clickable_selectors = "button:visible, a:visible, [role='button']:visible, .mat-card:visible, .card:visible"
        elements = await page.locator(clickable_selectors).all()
        
        for el in elements[:10]: # จำกัดที่ 10 เพื่อไม่ให้ค้าง
            try:
                text = (await el.inner_text()).lower()
                # Generic Blacklist: ป้องกันการ Logout
                if any(x in text for x in ["log", "sign", "exit", "out"]): continue
                
                await el.click(timeout=1500)
                await page.wait_for_timeout(1000) # รอ Network ทำงาน
                await page.keyboard.press("Escape") # เคลียร์เผื่อมีอะไรเด้งมาบัง
            except: continue