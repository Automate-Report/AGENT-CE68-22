import re
import time
import urllib.parse
from playwright.sync_api import sync_playwright
import base64

from src.core.requester import Requester
from src.core.logger import setup_logger
from src.utils.load_file import load_file
from src.utils.path_helper import get_resource_path

class SQLiScanner:
    def __init__(self):
        self.logger = setup_logger("SQLi Scanner")
        self.requester = Requester()
        
        # 1. Payloads: เน้น Error-Based เพื่อให้เห็นผลชัดเจน (เอาไว้ทำ Screenshot)
        # ของจริงควรโหลดจากไฟล์ data/payloads/sqli/error_based.txt
        self.payloads = [
            "'", 
            "\"", 
            "';", 
            "')", 
            "' OR '1'='1",
            "admin' --",
            "' UNION SELECT 1, @@version -- "
        ]
        
        # 2. Database Error Signatures (ลายเซ็น Error ของแต่ละ DB)
        self.error_signatures = {
            "MySQL": [
                r"SQL syntax.*MySQL",
                r"Warning.*mysql_",
                r"valid MySQL result",
                r"MySqlClient\.",
            ],
            "PostgreSQL": [
                r"PostgreSQL.*ERROR",
                r"Warning.*\Wpg_",
                r"valid PostgreSQL result",
                r"Npgsql\.",
            ],
            "Microsoft SQL Server": [
                r"Driver.* SQL[\-\_\ ]*Server",
                r"OLE DB.* SQL Server",
                r"\bSQL Server[^&lt;&quot;]+Driver",
                r"Warning.*mssql_",
                r"\bSqlException\b",
            ],
            "Oracle": [
                r"\bORA-[0-9][0-9][0-9][0-9]",
                r"Oracle error",
                r"Oracle.*Driver",
            ],
            "Generic": [
                r"You have an error in your SQL syntax",
                r"Unclosed quotation mark",
                r"quoted string not properly terminated",
            ]
        }

    def scan(self, url: str, params: dict) -> list:
        """
        Main Logic: ยิง Request -> เช็ค Error Text -> ถ้าเจอเรียก Playwright มาถ่ายรูป
        """
        findings = []
        self.logger.info(f"[*] Starting SQLi Scan on: {url}")

        if not params:
            return findings

        for param_key, original_value in params.items():
            self.logger.info(f"    -> Testing Parameter: {param_key}")
            
            for payload in self.payloads:
                # สร้าง Params สำหรับโจมตี
                attack_params = params.copy()
                attack_params[param_key] = payload
                
                try:
                    # 1. ยิง Request (ใช้ Requester ปกติ เร็ว!)
                    response = self.requester.get(url, params=attack_params)
                    
                    # 2. ตรวจสอบว่า Response มี Error Database ไหม
                    matched_db, error_msg = self._check_error_signatures(response.text)
                    
                    if matched_db:
                        self.logger.info(f"       [!!!] Potential SQLi Found! ({matched_db})")
                        self.logger.info(f"             Payload: {payload}")
                        
                        # 3. VERIFICATION & EVIDENCE
                        # เรียก Playwright มาเปิดดูของจริง + ถ่ายรูป Highlight Error
                        proof_data = self._verify_and_capture(response.url, error_msg)
                        
                        findings.append({
                            "url": url,
                            "param": param_key,
                            "payload": payload,
                            "type": "Error-Based SQLi",
                            "db_type": matched_db,
                            "confirmed": True,
                            "evidence_snippet": error_msg,
                            "screenshot": proof_data.get("screenshot")
                        })
                        
                        # เจอ 1 Payload ที่ทำ Error ได้ ก็หยุด Param นี้เลย (พอแล้ว)
                        break 
                        
                except Exception as e:
                    self.logger.error(f"       [-] Request error: {e}")

        return findings

    def _check_error_signatures(self, content: str) -> tuple:
        """
        เช็คว่าใน Response Body มีข้อความ Error ที่เรารู้จักไหม
        Returns: (DB_Type, Matched_String)
        """
        for db_type, regexes in self.error_signatures.items():
            for regex in regexes:
                match = re.search(regex, content, re.IGNORECASE)
                if match:
                    # คืนค่าประเภท DB และข้อความที่เจอ (เอาไป Highlight)
                    return db_type, match.group(0)
        return None, None

    def _verify_and_capture(self, url: str, error_text: str) -> dict:
        """
        ใช้ Playwright เปิด URL เพื่อถ่ายรูปและ Highlight Text ที่เป็น Error
        """
        result = {"screenshot": None}
        self.logger.info("       [..] Capturing evidence with Playwright...")

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(channel="chrome", headless=True)
                page = browser.new_page(ignore_https_errors=True)
                
                page.goto(url, wait_until="load", timeout=10000)
                
                # --- [TRICK] Highlight Error Text ---
                # เราจะ Inject JS เพื่อค้นหา Text ที่เป็น Error แล้วตีกรอบแดง
                try:
                    # Escape ตัวอักษรพิเศษใน error_text ก่อนส่งเข้า JS
                    safe_text = error_text.replace("'", "\\'").replace("\n", " ")
                    
                    page.evaluate(f"""
                        () => {{
                            const searchText = '{safe_text}';
                            const xpath = "//*[contains(text(),'" + searchText + "')]";
                            const matchingElement = document.evaluate(xpath, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
                            
                            if (matchingElement) {{
                                // เจอ Element ที่มี Error -> ตีกรอบแดง
                                matchingElement.style.border = "5px solid red";
                                matchingElement.style.backgroundColor = "yellow";
                                matchingElement.style.color = "red";
                                matchingElement.style.fontWeight = "bold";
                                matchingElement.scrollIntoView({{block: "center", behavior: "smooth"}});
                            }} else {{
                                // ถ้าหาไม่เจอ (อาจจะอยู่ใน source code แต่ไม่ render)
                                // ให้สร้างกล่องแจ้งเตือนลอยขึ้นมาแทน
                                const div = document.createElement('div');
                                div.style.cssText = 'position:fixed;top:10px;left:10px;background:red;color:white;padding:20px;z-index:99999;font-size:20px;border:3px solid yellow;';
                                div.innerText = "SQL Error Found in Source: " + searchText;
                                document.body.appendChild(div);
                            }}
                        }}
                    """)
                    
                    # รอให้ Render ทัน
                    page.wait_for_timeout(1000)
                    
                    # ถ่ายรูป
                    screenshot_bytes = page.screenshot(type="jpeg", quality=70, full_page=False)
                    result["screenshot"] = base64.b64encode(screenshot_bytes).decode('utf-8')
                    
                except Exception as e:
                    self.logger.warning(f"       [-] Highlight failed: {e}")

                browser.close()
        except Exception as e:
            self.logger.error(f"       [-] Verification failed: {e}")
            
        return result