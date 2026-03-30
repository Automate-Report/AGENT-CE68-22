# HTTP Client Wrapper
# จัดการ Proxy, Timeout, Retry

# security-worker/core/requester.py

import requests
import urllib3

from src.core.logger import setup_logger

# ปิด Warning กรณีเทสกับเว็บ HTTPS ที่ไม่มี Cer
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class Requester:
    def __init__(self, logger = None):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "SecurityWorker-Agent/1.0 (Educational)",
            "Accept": "*/*"
        })
        self.timeout = 10
        self.logger = logger or setup_logger("Requester")

    def get(self, url, params=None):
        try:
            return self.session.get(url, params=params, timeout=self.timeout, verify=False)
        except requests.RequestException as e:
            self.logger.error(f"[!] Request Error (GET): {e}")
            return None

    def post(self, url, data=None, json=None):
        try:
            return self.session.post(url, data=data, json=json, timeout=self.timeout, verify=False)
        except requests.RequestException as e:
            self.logger.error(f"[!] Request Error (POST): {e}")
            return None
    
    def send(self, method: str, url: str, payload_data: dict = None, content_type: str = "form", timeout: int = 10):
        """
        ส่ง Request ตาม Method และ Content-Type ที่กำหนด
        content_type: 'form' (x-www-form-urlencoded) หรือ 'json' (application/json)
        """
        try:
            method = method.upper()
            
            # --- [NEW] URL Path Rewriting for IDOR/Path fuzzing ---
            actual_payload = {}
            if payload_data:
                from urllib.parse import urlparse, urlunparse
                parsed = urlparse(url)
                parts = parsed.path.split('/')
                
                has_path_injection = False
                for k, v in payload_data.items():
                    if str(k).startswith("path_id_"):
                        try:
                            idx = int(k.split("_")[-1])
                            if 0 <= idx < len(parts):
                                parts[idx] = str(v)
                                has_path_injection = True
                        except: pass
                    else:
                        actual_payload[k] = v
                
                if has_path_injection:
                    new_path = '/'.join(parts)
                    # Preserve original query parameters that were already in the URL
                    url = urlunparse((parsed.scheme, parsed.netloc, new_path, parsed.params, parsed.query, parsed.fragment))
            else:
                actual_payload = payload_data
            # ------------------------------------------------------

            if method == "GET":
                return self.session.get(url, params=actual_payload, timeout=timeout, verify=False)
            
            # สำหรับ POST, PUT, PATCH, DELETE
            if content_type == "json":
                return self.session.request(method, url, json=actual_payload, timeout=timeout, verify=False)
            else:
                return self.session.request(method, url, data=actual_payload, timeout=timeout, verify=False)
                
        except Exception as e:
            self.logger.error(f"[Requester] ❌ Exception in send: {e}")
            return None
        
    def set_cookies(self, cookies):
        try:
            # 🚩 [เพิ่ม] ล้างคุกกี้เก่าทิ้งก่อน เพื่อให้แน่ใจว่าใช้ของใหม่จาก AuthHandler เท่านั้น
            self.session.cookies.clear() 

            if isinstance(cookies, list):
                for cookie in cookies:
                    # ตรวจสอบ Domain ให้ตรงกับ Target เพื่อป้องกันคุกกี้ไม่ถูกส่ง
                    self.session.cookies.set(cookie['name'], cookie['value'])
                self.logger.info(f"[Requester] 🍪 {len(cookies)} cookies injected and session cleared.")
            
            elif isinstance(cookies, dict):
                requests.utils.add_dict_to_cookiejar(self.session.cookies, cookies)
                self.logger.info(f"[Requester] 🍪 Cookies injected from dictionary.")
                
        except Exception as e:
            if self.logger:
                self.logger.error(f"[Requester] ❌ Failed to set cookies: {e}")

    def set_header(self, name, value):
        """
        ตั้งค่า Header ให้กับ Session เพื่อใช้ในทุก Request ต่อจากนี้
        """
        try:
            self.session.headers.update({name: value})
            self.logger.info(f"[Requester] 💉 Header set: {name}")
        except Exception as e:
            self.logger.error(f"[Requester] ❌ Failed to set header: {e}")