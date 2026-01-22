import requests
import sys
import time
import threading
from src.core import AuthManager, settings

class APIClient:
    def __init__(self, auth_manager: AuthManager):
        self.auth = auth_manager

    def send_heartbeat(self):
        if not self.auth.token:
            return False
        try:
            headers =self.auth.get_headers()

            url = f"{settings.backend_url}{settings.HEART_BEAT_ENDPOINT}"

            print(url)

            response = requests.post(url, headers=headers, timeout=5)


            if response.status_code == 200:
                print(f"💓 Heartbeat OK")
                return True
            
            elif response.status_code == 401:
                print("⚠️ Heartbeat 401: Token Expired. Renewing...")
                if self.auth.verify_worker(): # ลองต่ออายุ
                    return self.send_heartbeat() # ส่งใหม่
            
            elif response.status_code == 403:
                print("❌ Heartbeat 403: Access Revoked!")
                self.hard_reset("Server rejected heartbeat (Key Revoked).")

        except Exception as e:
            print(f"⚠️ Heartbeat Failed (Network Error): {e}")
        
        return False
    
    def start_heartbeat_loop(self):
        """รัน Heartbeat เป็น Background Thread"""
        def loop():
            while True:
                # ถ้ายังไม่มี Token (ยังไม่ Login) ให้รอ
                if self.auth.token:
                    self.send_heartbeat()
                
                # ส่งทุกๆ 30 วินาที (ปรับตามต้องการ)
                time.sleep(30) 

        # สร้าง Thread และสั่งรัน (Daemon=True คือถ้าปิดโปรแกรมหลัก Thread นี้จะดับด้วย)
        hb_thread = threading.Thread(target=loop, daemon=True)
        hb_thread.start()


    def post(self, endpoint, data):
        """POST Request"""
        # Check ว่ามี Token รึยัง
        if not self.auth.token:
            if not self.auth.verify_worker():
                return None

        # POST Request
        url = f"{settings.backend_url}{endpoint}"
        response = requests.post(url, json=data, headers=self.auth.get_headers())

        # Error handler
        if response.status_code == 401 or response.status_code == 403 or response.status_code == 500:
            print("Token Expired! Renewing...")
            if self.auth.verify_worker():
                print("✅ Re-handshake success. Resuming work.")
                response = requests.post(url, json=data, headers=self.auth.get_headers())
            else:
                print("❌ CRITICAL: Access Key is invalid/revoked by Server.")
                print("🛑 Agent is stopping now...")
                settings.reset()
                self.auth.reset()
                time.sleep(10)
                sys.exit(1)

        return response