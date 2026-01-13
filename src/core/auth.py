import requests
import traceback
import json
from src.config.settings import settings


class AuthManager:
    def __init__(self):
        self.token = None

    def verify_worker(self):
        """แลก Access Key เป็น JWT Token (Debug Mode)"""
        try: 
            url = f"{settings.backend_url}{settings.VERIFY_ENDPOINT}"
            payload = {
                "worker_id": settings.worker_id,
                "key": settings.access_key,
                "hostname": settings.hostname
            }

            # [DEBUG 1] ดูสิ่งที่กำลังจะส่งไป
            # print(f"--- DEBUG REQUEST ---")
            # print(f"URL: {url}")
            # print(f"Payload: {json.dumps(payload, indent=2)}") 

            response = requests.post(url, json=payload, timeout=5) # ใส่ timeout กันค้าง
            
            # [DEBUG 2] ดูสิ่งที่เซิฟเวอร์ตอบกลับมา
            # print(f"--- DEBUG RESPONSE ---")
            # print(f"Status Code: {response.status_code}")
            # print(f"Response Body: {response.text}") # ใช้ .text เพื่อดู raw data ก่อนแปลง json

            if response.status_code == 200:
                print("Verified Success")
                data = response.json()
                self.token = data.get("token")
                return True
            
            # [DEBUG 3] ถ้าไม่ 200 ให้ print เตือน
            # print(f"Failed to verify. Server returned: {response.status_code}")
            return False

        except Exception as e:
            # [DEBUG 4] ปริ้น Error จริงๆ ออกมาดู
            # print(f"!!! CRASH !!!: {e}")
            # print(traceback.format_exc()) # ปริ้น Stack trace เต็มๆ
            return False

    def get_headers(self):
        """Header พร้อม Toekn"""
        return {"Authorization": f"Bearer {self.token}"}               

    def reset(self):
        self.token = None                                             