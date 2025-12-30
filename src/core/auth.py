import requests
from src.config import settings


class AuthManager:
    def __init__(self):
        self.token = None

    def verify_worker(self):
        """แลก Access Key เป็น JWT Token"""
        try: 
            url = f"{settings.backend_url}{settings.VERIFY_ENDPOINT}"
            payload = {
                "worker_id": settings.worker_id,
                "key": settings.access_key,
                "hostname": settings.hostname
            }

            response = requests.post(url, json=payload)
            

            if response.status_code == 200:
                print("Verified Success")
                data = response.json()
                self.token = data.get("token")
                return True
            return False
        except:
            return False

    def get_headers(self):
        """Header พร้อม Toekn"""
        return {"Authorization": f"Bearer {self.token}"}               

    def reset(self):
        self.token = None                                             