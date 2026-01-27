import requests
from src.core.settings import settings


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

            response = requests.post(url, json=payload, timeout=10) 


            if response.status_code == 200:
                print("[Auth] Verified Success")
                data = response.json()
                self.token = data.get("token")
                return True
            else:
                print(f"[Auth] Verification Failed: {response.status_code}")
                print(response.text)
                return False

        except Exception as e:
            print(f"[Auth] Critical Error during verification: {e}")
            return False

    def get_headers(self):
        """Header พร้อม Toekn"""
        return {"Authorization": f"Bearer {self.token}"}               

    def reset(self):
        """ล้าง Token ออก ถ้า Key ถูก Revoked"""
        self.token = None                                             