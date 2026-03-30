import requests
import sys
import time
import threading
import socket
from src.core.auth import AuthManager
from src.core.settings import settings
from src.core.logger import setup_logger

class BackendBridge:
    def __init__(self, auth_manager: AuthManager):
        self.auth = auth_manager
        self.active_threads = 0
        self.logger = setup_logger("Bridge")

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

    def send_heartbeat(self):
        """ ส่ง Heartbeat พร้อม load data"""
        if not self.auth.token:
            return False
        
        try:
            headers =self.auth.get_headers()

            url = f"{settings.backend_url}{settings.heartbeat}"

            local_ip = self.get_internal_ip()

            payload = {
                "current_load": self.active_threads,
                "status": "online",
                "internal_ip": local_ip,
                "hostname": settings.hostname,
            }

            response = requests.post(url, json=payload, headers=headers, timeout=10)


            if response.status_code == 200:
                data = response.json()
                settings.maxThread = data.get("worker_threadnumber")
                self.logger.info(f"[Bridge] 💓 Heartbeat OK Load: {self.active_threads}/{settings.maxThread}")
                return True
            
            elif response.status_code == 401:
                self.logger.info("[Bridge] ⚠️ Heartbeat 401: Token Expired. Renewing...")
                if self.auth.verify_worker(): # ลองต่ออายุ
                    return self.send_heartbeat() # ส่งใหม่
            
            elif response.status_code == 403:
                self.logger.info("[Bridge] Heartbeat 403: Access Revoked!")
                self.emergency_shutdown("Server rejected heartbeat (Key Revoked).")

        except Exception as e:
            self.logger.error(f"[Bridge] ⚠️ Heartbeat Failed (Network Error): {e}")
        
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
        self.logger.info("[Bridge] 📡 Background Heartbeat started.")


    def post_result(self, data):
        """
        ส่งผลลัพธ์ของการ pen test ไปหา Backend
        """
        # Check ว่ามี Token รึยัง
        if not self.auth.token:
            if not self.auth.verify_worker():
                return None

        url = f"{settings.backend_url}{settings.send_pentest_log}"

        # 🔒 Encrypt the entire payload before sending
        try:
            from cryptography.fernet import Fernet
            import json
            
            cipher_suite = Fernet(settings.job_key.encode())
            raw_json_str = json.dumps(data)
            encrypted_payload = cipher_suite.encrypt(raw_json_str.encode()).decode()
            
            payload_to_send = {
                "job_id": data.get("job_id"),
                "encrypted_data": encrypted_payload
            }
        except Exception as e:
            self.logger.error(f"[Bridge] ❌ Encryption failed: {e}")
            return None

        for attempt in range(2):
            try:
                response = requests.post(url, json=payload_to_send, headers=self.auth.get_headers(), timeout=30)

                if response.status_code == 201 or response.status_code == 200:
                    return response
                
                if response.status_code in [401, 403]:
                    self.logger.info(f"[Bridge][Attempt {attempt+1}] Token Invalid. Renewing...")
                    if not self.auth.verify_worker():
                        self.emergency_shutdown("Access Revoked.")
                        break
                    continue
                if response.status_code >= 500:
                    self.logger.info(f"[Bridge][Attempt {attempt+1}] Server Error ({response.status_code}). Waiting 5s...")
                    time.sleep(5)
                    continue
                    
                self.logger.error(f"[Bridge][Attempt {attempt+1}] ❌ Failed with status {response.status_code}: {response.text}")
                break

            except requests.exceptions.RequestException as e:
                self.logger.error(f"[Bridge][Attempt {attempt+1}] 📡 Network Error: {e}")
                time.sleep(5)

        return None
    
    def update_status_job(self, data):
        # Check ว่ามี Token รึยัง
        if not self.auth.token:
            if not self.auth.verify_worker():
                return None
            
        url = f"{settings.backend_url}{settings.update_job_status}"


        for attempt in range(2):
            try:
                response = requests.post(url, json=data, headers=self.auth.get_headers(), timeout=30)

                if response.status_code == 201 or response.status_code == 200 or response.status_code == 210:
                    return response
                
                if response.status_code in [401, 403]:
                    self.logger.info(f"[Bridge][Attempt {attempt+1}] Token Invalid. Renewing...")
                    if not self.auth.verify_worker():
                        self.emergency_shutdown("Access Revoked.")
                        break
                    continue
                if response.status_code >= 500:
                    self.logger.info(f"[Bridge][Attempt {attempt+1}] Server Error ({response.status_code}). Waiting 5s...")
                    time.sleep(5)
                    continue

                self.logger.error(f"[Bridge][Attempt {attempt+1}] ❌ Failed with status {response.status_code}: {response.text}")
                break

            except requests.exceptions.RequestException as e:
                self.logger.error(f"[Bridge][Attempt {attempt+1}] 📡 Network Error: {e}")
                time.sleep(5)

        return None

    def fetch_next_job(self):
        """
        Poll jobs from Backend instead of directly from Redis.
        """
        if not self.auth.token:
            if not self.auth.verify_worker():
                return None
            
        url = f"{settings.backend_url}{settings.get_next_job}"

        try:
            response = requests.post(url, headers=self.auth.get_headers(), timeout=10)

            if response.status_code == 200:
                data = response.json()
                if data:  # could be null if no job
                    return data
                return None
            
            # Backend could return 404 or empty 200 when queue is empty
            if response.status_code == 404:
                return None
            
            if response.status_code in [401, 403]:
                self.logger.info("[Bridge] Token Invalid while polling. Renewing...")
                if not self.auth.verify_worker():
                    self.emergency_shutdown("Access Revoked.")
                return None
                
            self.logger.error(f"[Bridge] ❌ Failed to fetch job: status {response.status_code}: {response.text}")
            return None

        except requests.exceptions.Timeout:
            self.logger.debug(f"[Bridge] 📡 Polling timeout.")
        except requests.exceptions.RequestException as e:
            self.logger.error(f"[Bridge] 📡 Network Error while polling: {e}")

        return None

    def emergency_shutdown(self, reason):
        """กรณีเกิดข้อผิดพลาดร้ายแรง ให้หยุดการทำงานทันที"""
        self.logger.error(f"[Bridge] 🛑 EMERGENCY SHUTDOWN: {reason}")
        self.auth.reset()
        settings.reset()
        # หน่วงเวลาเล็กน้อยเพื่อให้ระบบบันทึก Log ก่อนจบโปรแกรม
        time.sleep(5)
        sys.exit(1)