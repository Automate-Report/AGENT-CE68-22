import requests
from src.core.auth import AuthManager
from src.config import settings

class APIClient:
    def __init__(self, auth_manager: AuthManager):
        self.auth = auth_manager

    def post(self, endpoint, data):
        """POST Request"""

        # Check ว่ามี Token รึยัง
        if not self.auth.token:
            if not self.auth.verify_worker():
                return None
            
        # POST Request
        url = f"{settings.BACKEND_URL}{endpoint}"
        response = requests.post(url, json=data, headers=self.auth.get_headers())

        # Error handler
        if response.status_code == 401:
            print("Token Expired! Renewing...")
            if self.auth.verify_worker():
                response = requests.post(url, json=data, headers=self.auth.get_headers())

        return response