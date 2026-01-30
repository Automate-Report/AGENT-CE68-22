import json
import time
import redis
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

        self.pool = redis.ConnectionPool(
            host=settings.redis_host,
            port=settings.redis_port,
            db=settings.redis_db,
            # password=settings.redis_password,
            decode_responses=True # สำคัญ: เพื่อให้ได้ข้อมูลเป็น string ไม่ใช่ bytes
        )

        self.redis_client = redis.Redis(connection_pool=self.pool)
        self.queue_name = f"system:queue:work:{settings.worker_id}"
        self.executor = ThreadPoolExecutor(max_workers=settings.maxThread)
        self.logger = setup_logger("Worker Engine")

    def run_task(self, job_data: dict):
        """
        Wrapper สำหรับการรันงานใน Thread
        """
        job_id = job_data.get("job_id")
        try:
            # เพิ่มจำนวน Thread ที่กำลังทำงาน (เพื่อให้ Heartbeat ส่งค่าที่ถูกต้อง)
            self.bridge.active_threads += 1
            self.logger.info(f"[Worker Engine][Job {job_id}] Processing...")

            orchestrator = ScanOrchestrator(job_data)
            scan_result = orchestrator.run_workflow()

            print(scan_result)
            
            # ส่ง pen test log กลับไปที่ Backend
            self.bridge.post_result(scan_result)

        except Exception as e:
            self.logger.error(f"[Worker Engine][Job {job_id}] Error: {e}")
        finally:
            # ลดจำนวน Thread เมื่อจบงาน (ไม่ว่าจะสำเร็จหรือพัง)
            self.bridge.active_threads -= 1
            self.logger.info(f"[Worker Engine][Job {job_id}] Done. (Active Threads: {self.bridge.active_threads})")

    def start(self):
        """เริ่มต้นการทำงานของ Worker"""
        self.logger.info(f"[Worker Engine] 🚀 Initializing Worker Engine [ID: {settings.worker_id}]")
        
        # 1. ยืนยันตัวตนก่อน
        if not self.auth.verify_worker():
            self.logger.info("[Worker Engine] ❌ Authentication Failed! Exiting...")
            return

        # 2. เริ่มส่ง Heartbeat (Background Thread)
        self.bridge.start_heartbeat_loop()

        # 3. เริ่มดึงงานจาก Redis (Main Loop)
        self.logger.info(f"[Worker Engine] 📡 Waiting for jobs in {self.queue_name}...")
        try:
            while True:
                # ใช้ blpop เพื่อรอรับงานแบบ Blocking (ไม่กิน CPU)
                # จะคืนค่าเป็น tuple (queue_name, data)
                task_tuple = self.redis_client.blpop(self.queue_name, timeout=0)
                
                if task_tuple:
                    raw_data = task_tuple[1]
                    try:

                        job_data = json.loads(raw_data)
                        self.logger.debug(f"[Worker Engine] DEBUG: job_data content is {job_data}")
                        job_id = job_data.get("job_id")

                        if job_id is None:
                            self.logger.info("[Worker Engine] ❌ Error: job_id is missing in payload")
                            return
                        
                        # ส่งงานเข้าไปใน Thread Pool
                        # หาก Thread เต็ม งานจะเข้าคิวรออัตโนมัติ
                        self.executor.submit(self.run_task, job_data)
                        self.logger.info("[Worker Engine] 📦 New Job Received: {job_id}")
                        payload = {
                            "job_id": job_id,
                            "status": "running"
                        }
                        self.bridge.update_status_job(payload)

                    except json.JSONDecodeError:
                        self.logger.error("[Worker Engine] ❌ Error: Could not decode JSON")

        except KeyboardInterrupt:
            self.logger.error("[Worker Engine] 🛑 Worker is shutting down...")
            self.executor.shutdown(wait=True)

