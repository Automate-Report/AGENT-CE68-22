import requests
from src.config import settings

class AuthManager:
    def __init__(self):
        self.token = None

    def verify_worker(self):
        """แลก Access Key เป็น JWT Token"""
        try: 
            url = f"{settings.BACKEND_URL}{settings.VERIFY_ENDPOINT}"
            payload = {
                "worker_id": settings.WORKER_ID,
                "key": settings.ACCESS_KEY,
                "hostname": settings.HOSTNAME
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