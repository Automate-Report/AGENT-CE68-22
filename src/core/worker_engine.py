import json
import time
import redis
from concurrent.futures import ThreadPoolExecutor

from src.core.auth import AuthManager
from src.core.settings import settings
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

        self.queue_name = f"queue:worker:{settings.worker_id}"
        
        self.executor = ThreadPoolExecutor(max_workers=settings.maxThread)

    def run_task(self, job_data: dict):
        """
        Wrapper สำหรับการรันงานใน Thread
        """
        job_id = job_data.get("id")
        try:
            # เพิ่มจำนวน Thread ที่กำลังทำงาน (เพื่อให้ Heartbeat ส่งค่าที่ถูกต้อง)
            self.bridge.active_threads += 1
            print(f"🛠️ [Job {job_id}] Processing...")

            orchestrator = ScanOrchestrator(job_data)
            scan_result = orchestrator.run_workflow()
            
            # จำลองการทำงาน
            # time.sleep(5) 
            
            # ส่ง Report กลับไปที่ Backend
            self.bridge.post_result(scan_result)

        except Exception as e:
            print(f"❌ [Job {job_id}] Error: {e}")
        finally:
            # ลดจำนวน Thread เมื่อจบงาน (ไม่ว่าจะสำเร็จหรือพัง)
            self.bridge.active_threads -= 1
            print(f"✅ [Job {job_id}] Done. (Active Threads: {self.bridge.active_threads})")

    def start(self):
        """เริ่มต้นการทำงานของ Worker"""
        print(f"🚀 Initializing Worker Engine [ID: {settings.worker_id}]")
        
        # 1. ยืนยันตัวตนก่อน
        if not self.auth.verify_worker():
            print("❌ Authentication Failed! Exiting...")
            return

        # 2. เริ่มส่ง Heartbeat (Background Thread)
        self.bridge.start_heartbeat_loop()

        # 3. เริ่มดึงงานจาก Redis (Main Loop)
        print(f"📡 Waiting for jobs in {self.queue_name}...")
        try:
            while True:
                # ใช้ blpop เพื่อรอรับงานแบบ Blocking (ไม่กิน CPU)
                # จะคืนค่าเป็น tuple (queue_name, data)
                task_tuple = self.redis_client.blpop(self.queue_name, timeout=0)
                
                if task_tuple:
                    _, raw_data = task_tuple
                    job_data = dict(json.loads(raw_data))
                    
                    print(f"📦 New Job Received: {job_data.get('id')}")

                    # ส่งงานเข้าไปใน Thread Pool
                    # หาก Thread เต็ม งานจะเข้าคิวรออัตโนมัติ
                    self.executor.submit(self.run_task, job_data)

        except KeyboardInterrupt:
            print("\n🛑 Worker is shutting down...")
            self.executor.shutdown(wait=True)

