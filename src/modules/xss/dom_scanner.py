# modules/xss/dom_scanner.py
from playwright.sync_api import sync_playwright, Page, Locator
import time

from src.core.logger import setup_logger
from .dom.page_handler import DOMPageHandler

class DOMScanner:
    def __init__(self):
        self.logger = setup_logger("XSS DOM Scanner")
        self.handler = DOMPageHandler(debug_mode=True)

        self.payloads = [
            "<img src=x onerror=alert(1)>", 
            "<iframe src='javascript:alert(1)'></iframe>",
            "\"><img src=x onerror=alert(1)>"
        ]
        self.debug_mode = True
        self.scan_timeout = 60
    
    def _fuzz_url_fragments(self, page: Page, url: str):
        """
        [NEW] โจมตีผ่าน URL Fragment (Source-based XSS)
        """
        if self.debug_mode:
            self.logger.info(f"       [+] Starting URL Fragment Fuzzing (Source-based XSS)...")
        
        # แยกประเภท Payload ให้ครอบคลุมทุก Sink
        url_payloads = [
            # 1. HTML Context (สำหรับ document.write, innerHTML)
            "#<img src=x onerror=alert(1)>",
            "#<svg/onload=alert(1)>",
            
            # 2. Javascript Execution Context (สำหรับ eval, setTimeout, Function)
            "#alert(1)",            # <--- ตัวนี้สำคัญมากสำหรับ Firing Range!
            "#;alert(1)",           # เผื่อมีการต่อ String
            "#-alert(1)-",          # เผื่ออยู่ในสมการเลข
            
            # 3. URI Sinks (สำหรับ location.href, assign, replace)
            "#javascript:alert(1)" 
        ]

        for payload in url_payloads:
            if self.handler.scan_state["alert_triggered"]: return

            try:
                target_url = f"{url}{payload}" if "?" not in url else f"{url}&{payload[1:]}"
                page.goto(target_url, wait_until="domcontentloaded", timeout=3000)
                if "#" in payload: page.reload(timeout=3000)
                page.wait_for_timeout(500)
            except: pass
    
    def _run_scan_logic(self, page: Page, url: str, params: dict, start_time: float) -> list:
        """
        ควบคุม Flow การทำงาน: ไปที่ URL -> ปิด Popup -> วนลูป Params
        """
        findings = []

        # Navigate
        try:
            if self.debug_mode: 
                self.logger.debug(f"    [DEBUG] Navigating to {url}...")
            page.goto(url, wait_until="networkidle", timeout=15000)
        except:
            self.logger.error("       [!] Navigation timeout, but continuing...")

        # Pre-flight Checks
        self.handler.handle_popups(page)
        self.handler.wait_for_inputs(page)

        # --- PHASE 1: URL Source Fuzzing ---
        self.handler.reset_state()
        self._fuzz_url_fragments(page, url)

        if self.handler.scan_state["alert_triggered"]:
            findings.append(self._create_finding_dict(url, "URL_FRAGMENT", "Source-based"))
            self.logger.info(f"       [!!!] Vulnerability Found via URL Fragment!")
            return findings

        # --- PHASE 2: Input Fuzzing ---
        for param_key in params.keys():
            if time.time() - start_time > self.scan_timeout:
                break

            if self.handler.scan_state["alert_triggered"]: break

            self.logger.info(f"    -> Testing Parameter: {param_key}")

            self.handler.reset_state()

            self._process_input(page, param_key)

            if self.handler.scan_state["alert_triggered"]:
                self.logger.info("       [..] Alert detected! Waiting for evidence capture...")
                time.sleep(2) # รอ Handler ถ่ายรูปให้เสร็จชัวร์ๆ
                
                findings.append(self._create_finding_dict(url, param_key, "DOM_BASED"))
                self.logger.info(f"       [+] Vulnerability Recorded for {param_key}")
                break 

        return findings

    def _create_finding_dict(self, url, param, context):
        """Helper function เพื่อสร้าง Dictionary ผลลัพธ์ให้เป็นระเบียบ"""
        return {
            "url": url,
            "param": param,
            "payload": "Multiple (DOM)",
            "context": context,
            "confirmed": True,
            "details": self.handler.scan_state["last_message"],
            "screenshot": self.handler.scan_state["screenshot"]
        }

    def _process_input(self, page: Page, param_key: str) -> bool:
        """
        Strategy: ลองหา Input ตามชื่อก่อน ถ้าไม่เจอให้ใช้ Fallback (Fuzz All)
        """
        # 1. Try Specific Target
        target = self._find_specific_element(page, param_key)
        
        if target:
            if self.debug_mode: 
                self.logger.debug(f"       [DEBUG] Injecting payloads into: {target}")
            self._inject_payloads(target, page)
        else:
            self.logger.info(f"       [-] Specific input '{param_key}' not found. Switching to Fuzzing Mode...")
            # 2. Fallback: Fuzz All Visible Inputs
            self._fuzz_all_visible_inputs(page)

    def _find_specific_element(self, page: Page, param_key: str) -> Locator:
        """
        ค้นหา Element ด้วย Selector หลายรูปแบบ
        """
        selectors = [
            f"#{param_key}",            # ID
            f"[name='{param_key}']",    # Name
            f"input[placeholder*='{param_key}']",
            f"[id*='{param_key}']"
        ]
        
        for sel in selectors:
            try:
                locator = page.locator(sel).first
                if locator.is_visible(timeout=1000):
                    self.logger.info(f"       [+] Found target via selector: {sel}")
                    return locator
            except: continue
        return None

    def _fuzz_all_visible_inputs(self, page: Page):
        """
        ค้นหา Input ที่มองเห็นได้ทั้งหมด แล้วยิง Payload
        """
        try:
            inputs = page.locator("input:visible, textarea:visible").all()
            # กรอง input ที่ไม่น่าสนใจออก
            valid_inputs = [
                inp for inp in inputs 
                if inp.get_attribute("type") not in ["checkbox", "radio", "submit", "hidden", "button"]
            ]

            if not valid_inputs:
                self.logger.debug("       [!] [DEBUG] No visible inputs found to fuzz.")
                self._take_debug_screenshot(page, "no_inputs_found")
                return
            
            self.logger.info(f"       [!] Fuzzing {len(valid_inputs)} visible inputs...")
            for inp in valid_inputs:
                self._inject_payloads(inp, page)
                
        except Exception as e:
            self.logger.error(f"       [-] Fuzzing error: {e}")

    def _inject_payloads(self, locator: Locator, page: Page):
        """
        ทำการพิมพ์ Payload -> กด Enter -> และไล่กดปุ่ม Submit
        """
        for payload in self.payloads:
            try:
                # 1. พิมพ์ Payload
                locator.fill("") 
                locator.fill(payload)
                
                # 2. ลองกด Enter (เผื่อเป็น Search form)
                locator.press("Enter")
                page.wait_for_timeout(500)
                
                # 3. [NEW] ท่าไม้ตาย: ไล่กดปุ่ม Submit/Button ที่อยู่ใกล้เคียง
                self._trigger_submit_buttons(page)
                
                page.wait_for_timeout(500) # รอ JS ทำงาน
            except:
                pass

    def _trigger_submit_buttons(self, page: Page):
        """
        พยายามหาปุ่มที่น่าจะเป็นปุ่มส่งข้อมูล แล้วกดมัน
        """
        try:
            # หาปุ่มที่เป็น Submit หรือ Button ทั่วไป
            # (ใน XSS Game ปุ่มเป็น <button>Share status</button>)
            buttons = page.locator("button, input[type='submit'], input[type='button']").all()
            
            # กรองปุ่มที่มองเห็นได้ (Visible)
            visible_buttons = [b for b in buttons if b.is_visible()]
            
            # ถ้ามีปุ่มเยอะเกินไป (เช่นเกิน 5 ปุ่ม) อาจจะกดมั่ว ให้เลือกกดเฉพาะปุ่มที่มีคำว่า Save, Submit, Share, Login, Go
            # แต่สำหรับ XSS Game กดแม่มทุกปุ่มเลยก็ได้ครับถ้ามีไม่เยอะ
            for btn in visible_buttons:
                # เช็ค text ในปุ่มหน่อยก็ดี (Optional)
                # text = btn.inner_text().lower()
                # if any(x in text for x in ['share', 'post', 'submit', 'search', 'go', 'login']):
                
                try:
                    btn.click(timeout=500)
                except:
                    pass
        except:
            pass

    def scan(self, url: str, params: dict) -> list:
        """
        Main Entry Point: จัดการ Lifecycle ของ Browser และรวบรวมผลลัพธ์
        """
        findings = []
        self.logger.info(f"[*] Starting DOM Scan on: {url}")
        start_time = time.time()

        with sync_playwright() as p:
            # 1. Setup Browser
            browser = p.chromium.launch(channel="chrome", headless=False, slow_mo=100) # Debug Mode
            context = browser.new_context(ignore_https_errors=True)
            

            try:

                page = self.handler.setup_page(context)
           
                findings = self._run_scan_logic(page, url, params, start_time)

            except Exception as e:
                self.logger.error(f"[-] DOM Scan Critical Error: {e}")

            finally:
                if self.debug_mode:
                    self.logger.debug(f"[*] [DEBUG] Closing Browser session...")
                context.close()
                browser.close()
            
        return findings