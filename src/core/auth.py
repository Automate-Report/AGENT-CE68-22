import requests
from src.core.settings import settings
from src.core.logger import setup_logger

class AuthManager:
    def __init__(self):
        self.token = None
        self.logger = setup_logger("AuthManager")

    def verify_worker(self):
        """แลก Access Key เป็น JWT Token"""
        try: 
            url = f"{settings.backend_url}{settings.verify_endpoint}"
            payload = {
                "worker_id": settings.worker_id,
                "key": settings.access_key,
                "hostname": settings.hostname
            }

            response = requests.post(url, json=payload, timeout=10) 


            if response.status_code == 200:
                self.logger.info("[Auth] Verified Success")
                data = response.json()
                self.token = data.get("token")
                return True
            else:
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