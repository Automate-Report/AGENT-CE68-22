import time
from playwright.sync_api import Page

def dismiss_obstacles(page: Page):
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
            if el.is_visible(timeout=300):
                el.click()
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
        page.evaluate(aggressive_script)
    except: pass

def trigger_hidden_elements(page: Page):
    """คลิกปุ่มที่มักจะซ่อน Input ไว้ เช่น ปุ่มค้นหา"""
    triggers = [".mat-search_icon-search", "button[aria-label*='Search']", ".search-button", "[id*='search']"]
    for s in triggers:
        try:
            el = page.locator(s).first
            if el.is_visible(timeout=400):
                el.click()
                page.wait_for_timeout(500)
        except: continue

def safe_wait(page: Page, timeout=1000):
    """การรอที่ปลอดภัยและไม่ทำให้ระบบค้าง"""
    try:
        page.wait_for_timeout(timeout)
    except: pass