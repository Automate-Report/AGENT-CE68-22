import json
import redis
import asyncio
from concurrent.futures import ThreadPoolExecutor

from src.core.auth import AuthManager
from src.core.settings import settings
from src.core.logger import setup_logger
from src.networking.bridge import BackendBridge
from src.scanner.scan_engine import ScanOrchestrator

class WorkerEngine:
    def __init__(self):
        self.auth = AuthManager()
        self.bridge = BackendBridge(self.auth)

        # Removed direct Redis connection
        self.queue_name = f"system:queue:work:{settings.worker_id}"
        self.executor = ThreadPoolExecutor(max_workers=settings.maxThread)
        self.logger = setup_logger("Worker Engine")

    def run_task(self, job_data: dict):
        """
        Wrapper สำหรับการรันงานใน Thread
        """
        job_name = job_data.get("name")
        try:
            # เพิ่มจำนวน Thread ที่กำลังทำงาน (เพื่อให้ Heartbeat ส่งค่าที่ถูกต้อง)
            self.bridge.active_threads += 1
            self.logger.info(f"[Worker Engine][Job {job_name}] Processing...")

            orchestrator = ScanOrchestrator(job_data)
            scan_result = asyncio.run(orchestrator.run_workflow())

            full_logs = scan_result.get("logs", "")
            self.logger.info(f"Job {job_name} generated {full_logs}")

            # ส่ง pen test log กลับไปที่ Backend
            self.bridge.post_result(scan_result)

        except Exception as e:
            self.logger.error(f"[Worker Engine][Job {job_name}] Error: {e}")
        finally:
            # ลดจำนวน Thread เมื่อจบงาน (ไม่ว่าจะสำเร็จหรือพัง)
            self.bridge.active_threads -= 1
            self.logger.info(f"[Worker Engine][Job {job_name}] Done. (Active Threads: {self.bridge.active_threads})")

    def start(self):
        """เริ่มต้นการทำงานของ Worker"""
        self.logger.info(f"[Worker Engine] 🚀 Initializing Worker Engine [Name: {settings.worker_name}]")
        
        # 1. ยืนยันตัวตนก่อน
        if not self.auth.verify_worker():
            self.logger.info("[Worker Engine] ❌ Authentication Failed! Exiting...")
            return

        # 2. เริ่มส่ง Heartbeat (Background Thread)
        self.bridge.start_heartbeat_loop()

        # 3. เริ่มดึงงานจาก Backend (Main Loop)
        self.logger.info(f"[Worker Engine] 📡 Waiting for jobs from Backend API...")
        try:
            while True:
                # Poll data from the backend
                job_data = self.bridge.fetch_next_job()
                
                if job_data:
                    try:
                        self.logger.debug(f"[Worker Engine] DEBUG: job_data content is {job_data}")
                        job_id = job_data.get("job_id")
                        job_name = job_data.get("name")

                        if job_id is None:
                            self.logger.info("[Worker Engine] ❌ Error: job_id is missing in payload")
                            continue
                        
                        settings.maxThread = job_data.get("thread_number", settings.maxThread)
                        
                        # Decrypt credentials if present
                        if job_data.get("credential"):
                            try:
                                from cryptography.fernet import Fernet
                                cipher_suite = Fernet(settings.job_key.encode())
                                cred = job_data["credential"]
                                if cred.get("username"):
                                    cred["username"] = cipher_suite.decrypt(cred["username"].encode()).decode()
                                if cred.get("password"):
                                    cred["password"] = cipher_suite.decrypt(cred["password"].encode()).decode()
                                self.logger.info("[Worker Engine] 🔐 Decrypted credentials successfully")
                            except Exception as decrypt_err:
                                self.logger.error(f"[Worker Engine] ❌ Failed to decrypt credentials: {decrypt_err}")
                        
                        # ส่งงานเข้าไปใน Thread Pool
                        # หาก Thread เต็ม งานจะเข้าคิวรออัตโนมัติ
                        self.executor.submit(self.run_task, job_data)
                        self.logger.info(f"[Worker Engine] 📦 New Job Received: {job_name}")
                        payload = {
                            "job_id": job_id,
                            "status": "running"
                        }
                        self.bridge.update_status_job(payload)

                    except Exception as e:
                        self.logger.error(f"[Worker Engine] ❌ Error processing job: {e}")
                
                # Sleep to prevent spamming the backend if queue is empty
                import time
                time.sleep(settings.poll_interval)

        except KeyboardInterrupt:
            self.logger.error("[Worker Engine] 🛑 Worker is shutting down...")
            self.executor.shutdown(wait=True)

