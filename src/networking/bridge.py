import requests
import sys
import time
import threading
from src.core.auth import AuthManager
from src.core.settings import settings

class BackendBridge:
    def __init__(self, auth_manager: AuthManager):
        self.auth = auth_manager
        self.active_threads = 0

    def send_heartbeat(self):
        """ ส่ง Heartbeat พร้อม load data"""
        if not self.auth.token:
            return False
        
        try:
            headers =self.auth.get_headers()

            url = f"{settings.backend_url}{settings.HEART_BEAT_ENDPOINT}"

            payload = {
                "current_load": self.active_threads,
                "status": "online"
            }

            response = requests.post(url, json=payload, headers=headers, timeout=10)


            if response.status_code == 200:
                print(f"💓 Heartbeat OK Load: {self.active_threads}/{settings.maxThread}")
                return True
            
            elif response.status_code == 401:
                print("⚠️ Heartbeat 401: Token Expired. Renewing...")
                if self.auth.verify_worker(): # ลองต่ออายุ
                    return self.send_heartbeat() # ส่งใหม่
            
            elif response.status_code == 403:
                print("Heartbeat 403: Access Revoked!")
                self.emergency_shutdown("Server rejected heartbeat (Key Revoked).")

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
        print("📡 Background Heartbeat started.")


    def post_result(self, data):
        """
        ส่งผลลัพธ์ของการ pen test ไปหา Backend
        """
        # Check ว่ามี Token รึยัง
        if not self.auth.token:
            if not self.auth.verify_worker():
                return None

        url = f"{settings.backend_url}{settings.SUBMIT_TASK_ENDPOINT}"

        for attempt in range(2):
            try:
                response = requests.post(url, json=data, headers=self.auth.get_headers(), timeout=30)

                if response.status_code == 201 or response.status_code == 200:
                    return response
                
                if response.status_code in [401, 403]:
                    print(f"[Attempt {attempt+1}] Token Invalid. Renewing...")
                    if not self.auth.verify_worker():
                        self.emergency_shutdown("Access Revoked.")
                        break
                    continue
                if response.status_code >= 500:
                    print(f"Server Error ({response.status_code}). Waiting 5s...")
                    time.sleep(5)
                    continue

                print(f"❌ Failed with status {response.status_code}: {response.text}")
                break

            except requests.exceptions.RequestException as e:
                print(f"📡 Network Error: {e}")
                time.sleep(5)

        return None
    
    def emergency_shutdown(self, reason):
        """กรณีเกิดข้อผิดพลาดร้ายแรง ให้หยุดการทำงานทันที"""
        print(f"🛑 EMERGENCY SHUTDOWN: {reason}")
        self.auth.reset()
        settings.reset()
        # หน่วงเวลาเล็กน้อยเพื่อให้ระบบบันทึก Log ก่อนจบโปรแกรม
        time.sleep(5)
        sys.exit(1)