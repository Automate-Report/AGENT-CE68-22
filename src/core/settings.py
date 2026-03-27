import sys
import json
import os
import getpass
import requests
import socket

from cryptography.fernet import Fernet

from src.core.config_manager import EncryptedConfig
from src.core.logger import setup_logger

class Settings:
    #[Worker] ฝังใน template ก่อนส่งให้ user
    EMBEDDED_KEY = b'JimGiFbXqlAwUAXu2PM1_eATccCMR7uAoB0wfI2DMgQ='
    DELIMITER = b"|||HIDDEN_DATA|||"

    #[Worker] ชื่อ config
    CONFIG_FILE_NAME = "config.json" # ไฟล์เก็บค่าทั่วไปให้ user แก้ไขได้ 

    #[Exploits] ====================================================================
    USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    TIMEOUT = 10
    VERIFY_TIMEOUT = 5000  # 5 seconds for Playwright wait
    DEBUG = True



    def __init__(self):
         
        self.access_key = "KiNQSQODu7bNBv31aDCofvskfmM2Z-KYjtBz67pglOg"
        self.poll_interval = 5
        self.hostname = socket.gethostname()
        
        self.secure_store = EncryptedConfig("secret.dat")

        self.logger = setup_logger("Worker")

        # extract จาก exe
        self.worker_id = 1
        self.worker_name = ""
        self.maxThread = 2
        self.backend_url = "http://localhost:8000"
        self.redis_url = "redis://10.66.1.226:5678/1"
        

        self.get_worker_endpoint = "/workers/"
        self.verify_endpoint = "/workers/verify/"
        self.send_pentest_log = "/pentest-logs/" 
        self.heartbeat = "/workers/heartbeat/"
        self.update_job_status = "/jobs/update_status/"

    def setup(self):
        # load from config.json
        self._load_from_json_file()

        self.logger.info(f"Setup Worker.")

        # exteact 
        self._load_from_exe_overlay()

        # get access_key
        self._load_or_ask_access_key()
        self.logger.info(f"[Settings] Loaded: Worker {self.worker_name} | Poll: {self.poll_interval}s")

    def reset(self):
        self.access_key = None
        self.secure_store.remove_file()

    def _load_from_exe_overlay(self):
        """แกะ ID และ URL จากท้ายไฟล์ EXE"""
        try:
            exe_path = os.path.abspath(sys.argv[0])
            self.logger.debug(f"[Settings] Reading EXE from: {exe_path}")

            with open(exe_path, "rb") as f:
                content = f.read()
            
            pos = content.rfind(self.DELIMITER)
            
            if pos != -1:
                encrypted_data = content[pos + len(self.DELIMITER):]
                f = Fernet(self.EMBEDDED_KEY)
                data = json.loads(f.decrypt(encrypted_data))
                
                self.worker_id = data.get("WORKER_ID")
                self.worker_name = data.get("WORKER_NAME")
                self.maxThread = data.get("NUMBER_OF_THREADS", 1)
                self.backend_url = data.get("BACKEND_URL")
                
                self.redis_url = data.get("REDIS_URL")

                self.logger.debug(f"[Settings] Overlay Found: Worker {self.worker_name}")
            else:
                self.logger.debug(f"[Settings] ⚠️ Warning: ไม่พบ ID ที่ฝังมา (อาจจะรันแบบ Python Script ปกติ หรือไม่ได้ผ่าน Backend)")
        except Exception as e:
            self.logger.error(f"[Settings] ❌ Error reading EXE overlay: {e}")

    def _load_from_json_file(self):
        """อ่านค่า Config ที่ User แก้ไขได้"""
        self.logger.info("[settings] Load data from config.json.")
        if not os.path.exists(self.CONFIG_FILE_NAME):
            default_conf = {"POLL_INTERVAL": 5}
            with open(self.CONFIG_FILE_NAME, "w") as f:
                json.dump(default_conf, f, indent=4)
            self.poll_interval = 5
            self.logger.info(f"     > Create config.json file.")
            self.logger.info(f"     > Default Poll Interval: {self.poll_interval}s")
        else:
            try:
                with open(self.CONFIG_FILE_NAME, "r") as f:
                    data = json.load(f)
                    # ดึงเฉพาะค่าที่เราอนุญาตให้แก้
                    self.poll_interval = data.get("POLL_INTERVAL", 5)
                    self.logger.info(f"     > Poll Interval: {self.poll_interval}")
            except:
                self.logger.warning(f"      > ⚠️ config.json เสียหาย ใช้ค่า Default (5s)")
                self.poll_interval = 5

    def _load_or_ask_access_key(self):
        """จัดการ Access Key (Load -> Check -> Ask -> Save)"""
        # 1. ลองโหลดจากไฟล์ลับก่อน
        key = self.secure_store.load_access_key()

        if key:
            self.access_key = key
            return

        # 2. ถ้าไม่มี ให้ถาม User (Console Input)
        self.logger.info("[Settings] Security Check Required")
        self.logger.info("--------------------------")

        while not key:
            user_input = getpass.getpass(f"Enter Access Key for {self.worker_name}: ")
            if user_input.strip():
                key = user_input.strip()
        
        # 3. บันทึกเก็บไว้ (Encrypt) ครั้งหน้าจะได้ไม่ต้องถาม
        self.secure_store.save_access_key(key)
        self.access_key = key

# สร้าง Instance เดียวใช้ทั้งโปรแกรม
settings = Settings()
settings.setup()
