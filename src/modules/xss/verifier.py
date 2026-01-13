#Platwright check alert
from playwright.sync_api import sync_playwright
from core.logger import setup_logger

class XSSVerifier:
    def __init__(self):
        # ตั้งค่า Log
        self.logger = setup_logger("XSS Verifier")

    def verify(self, url: str, timeout: int = 5000) -> bool:
        """
        เปิด Browser จริงๆ เพื่อตรวจสอบว่า alert() เด้งขึ้นมาหรือไม่
        
        Args:
            url (str): URL ที่มี Payload ฝังอยู่แล้ว (Full Attack URL)
            timeout (int): เวลาสูงสุดที่จะรอ (millisecond)
            
        Returns:
            bool: True ถ้ามี Alert เด้ง (XSS สำเร็จ), False ถ้าเงียบ
        """
        is_vulnerable = False

        try:
            with sync_playwright() as p:
                # 1. Launch Browser (Headless = ไม่ต้องโชว์หน้าต่าง GUI เพื่อความเร็ว)
                browser = p.chromium.launch(headless=True)
                
                # สร้าง Context (เหมือนเปิด Incognito ใหม่ทุกครั้ง เพื่อความชัวร์)
                context = browser.new_context(ignore_https_errors=True)
                page = context.new_page()

                # --- หัวใจสำคัญ: ดักจับ Event 'dialog' ---
                # ถ้ามี alert(), confirm(), prompt() เด้งขึ้นมา ฟังก์ชันนี้จะทำงานทันที
                def handle_dialog(dialog):
                    nonlocal is_vulnerable
                    # เช็คข้อความใน alert ด้วยก็ได้ ถ้า payload เราใส่ alert(1) หรือ alert('XSS')
                    # if dialog.message == '1': 
                    self.logger.info(f"    [VERIFIER] 🚨 Alert Dialog Detected! Message: {dialog.message}")
                    is_vulnerable = True
                    
                    # กด OK เพื่อปิด Alert ไม่ให้ Browser ค้าง
                    dialog.accept()

                # ผูก Event Listener
                page.on("dialog", handle_dialog)

                # 2. ไปที่ URL เป้าหมาย
                self.logger.info(f"    [VERIFIER] Navigating to: {url}")
                try:
                    # waitUntil='load' คือรอให้หมุนติ้วๆ เสร็จ
                    # timeout คือถ้านานเกินกำหนดให้ตัดจบ (กันเว็บค้าง)
                    page.goto(url, wait_until='load', timeout=timeout)
                    
                    # รออีกนิดเผื่อเป็น DOM-based XSS ที่ทำงานช้า
                    page.wait_for_timeout(1000) 
                    
                except Exception as e:
                    # บางที alert เด้งแล้ว browser อาจจะตัด connection หรือ error
                    # แต่ถ้า is_vulnerable เป็น True แล้ว ก็ถือว่าผ่าน
                    if not is_vulnerable:
                        self.logger.warning(f"    [VERIFIER] Error during navigation: {e}")

                # 3. ปิด Browser
                browser.close()

        except Exception as e:
            self.logger.error(f"    [VERIFIER] System Error: {e}")

        return is_vulnerable