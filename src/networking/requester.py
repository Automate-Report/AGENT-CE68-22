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
    
    def send(self, method: str, url: str, payload_data: dict = None, content_type: str = "form"):
        """
        ส่ง Request ตาม Method และ Content-Type ที่กำหนด
        content_type: 'form' (x-www-form-urlencoded) หรือ 'json' (application/json)
        """
        try:
            method = method.upper()
            if method == "GET":
                return self.session.get(url, params=payload_data, timeout=10, verify=False)
            
            # สำหรับ POST, PUT, PATCH, DELETE
            if content_type == "json":
                return self.session.request(method, url, json=payload_data, timeout=10, verify=False)
            else:
                return self.session.request(method, url, data=payload_data, timeout=10, verify=False)
                
        except Exception as e:
            return None