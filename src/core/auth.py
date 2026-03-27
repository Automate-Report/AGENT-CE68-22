from http.client import HTTPException

import requests
import socket
from src.core.settings import settings
from src.core.logger import setup_logger

class AuthManager:
    def __init__(self):
        self.token = None
        self.logger = setup_logger("AuthManager")

    def get_internal_ip(self):
        """ดึง Local IP ของเครื่องที่ Worker กำลังรันอยู่"""
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            # ใช้ 8.8.8.8 เพื่อหา Route ที่ออกสู่ Network ได้ (ไม่ได้มีการส่งข้อมูลจริง)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
        except Exception:
            ip = "127.0.0.1"
        finally:
            s.close()
        return ip

    def verify_worker(self):
        """แลก Access Key เป็น JWT Token"""
        try: 
            url = f"{settings.backend_url}{settings.verify_endpoint}"

            local_ip = self.get_internal_ip()

            payload = {
                "worker_id": settings.worker_id,
                "key": settings.access_key,
                "hostname": settings.hostname,
                "internal_ip": local_ip
            }

            response = requests.post(url, json=payload, timeout=10) 

            if response.status_code == 200:
                self.logger.info("[Auth] Verified Success")
                data = response.json()
                self.token = data.get("token")
                return True
            elif response.status_code == 403:
                self.logger.error("[Auth] 403 Key Mismatch! Clearing invalid session...")
                self.reset()
                settings.reset()
            elif response.status_code == 420:
                self.logger.error("Worker has no owner, please download worker again to bind with your account.")
                self.reset()
                settings.reset()
            else:
                try:
                    error_detail = response.json().get("detail", "No detail provided")
                    self.logger.error(f"[Auth] Verification Failed: {response.status_code}")
                except:
                    self.logger.error(f"[Auth] Verification Failed: {response.status_code}")
                return False
            

        except Exception as e:
            self.logger.error(f"[Auth] Critical Error during verification: {e}")
            return False

    def get_headers(self):
        """Header พร้อม Toekn"""
        return {"Authorization": f"Bearer {self.token}"}               

    def reset(self):
        """ล้าง Token ออก ถ้า Key ถูก Revoked"""
        self.token = None                                             