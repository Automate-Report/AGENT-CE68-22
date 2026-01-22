# HTTP Client Wrapper
# จัดการ Proxy, Timeout, Retry

# security-worker/core/requester.py

import requests
import urllib3

from src.core import setup_logger

# ปิด Warning กรณีเทสกับเว็บ HTTPS ที่ไม่มี Cer
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class Requester:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "SecurityWorker-Agent/1.0 (Educational)",
            "Accept": "*/*"
        })
        self.timeout = 10
        self.logger = setup_logger("Requester")

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