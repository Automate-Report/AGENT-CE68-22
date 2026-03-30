import time
import asyncio
from playwright.async_api import Page

async def goto_with_retry(page: Page, url: str, wait_until: str = "networkidle", timeout: int = 15000, max_retries: int = 3, logger=None):
    """โหลดหน้าเว็บพร้อมระบบลองใหม่ (Retry) กรณีอินเทอร์เน็ตมีปัญหา เช่น ERR_NETWORK_CHANGED"""
    original_wait = wait_until
    if wait_until == "networkidle":
        wait_until = "load"
        
    last_error = None
    for attempt in range(max_retries):
        try:
            res = await page.goto(url, wait_until=wait_until, timeout=timeout)
            
            # ถ้าตั้งใจจะใช้ networkidle (มักจะมีปัญหากับ SPA) ให้เปลี่ยนเป็นรอ 2 วิหลังจาก load เสร็จ
            if original_wait == "networkidle":
                await page.wait_for_timeout(2000)
                
            return res
        except Exception as e:
            last_error = e
            if logger:
                logger.warning(f"⚠️ Navigation failed [{attempt+1}/{max_retries}] to {url}: {str(e)}")
            
            if attempt < max_retries - 1:
                await asyncio.sleep(2)
                
    raise last_error

async def dismiss_obstacles(page: Page):
    """เคลียร์ Pop-ups, Cookie Banners และ Overlays ทั้งหมด"""
    # 1. คลิกปุ่มปิด/ยอมรับที่พบบ่อย
    selectors = [
        "button:has-text('Accept')", "button:has-text('OK')", "button:has-text('Dismiss')",
        "button:has-text('Close')", "button:has-text('ยอมรับ')", "button[aria-label*='Close']",
        ".close-button", ".modal-close", ".cookie-banner__accept"
    ]
    for s in selectors:
        try:
            el = page.locator(s).first
            if await el.is_visible(timeout=300):
                await el.click()
        except: continue

    # 2. ลบ Overlay กีดขวางด้วย JavaScript (สำหรับ SPA อย่าง Juice Shop)
    aggressive_script = """
    () => {
        const overlays = document.querySelectorAll('.cdk-overlay-container, .modal-backdrop, [class*="overlay"], [class*="modal"]');
        overlays.forEach(el => el.remove());
        document.body.style.overflow = 'auto';
        document.documentElement.style.overflow = 'auto';
    }
    """
    try:
        await page.evaluate(aggressive_script)
    except: pass

async def trigger_hidden_elements(page: Page):
    """คลิกปุ่มที่มักจะซ่อน Input ไว้ เช่น ปุ่มค้นหา"""
    triggers = [".mat-search_icon-search", "button[aria-label*='Search']", ".search-button", "[id*='search']"]
    for s in triggers:
        try:
            el = page.locator(s).first
            if await el.is_visible(timeout=400):
                await el.click()
                await page.wait_for_timeout(500)
        except: continue

async def safe_wait(page: Page, timeout=1000):
    """การรอที่ปลอดภัยและไม่ทำให้ระบบค้าง"""
    try:
        await page.wait_for_timeout(timeout)
    except: pass