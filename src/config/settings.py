import sys
import json
import os
import getpass
import requests
import platform

from cryptography.fernet import Fernet
from src.core.config_manager import EncryptedConfig

class Settings:
    
    EMBEDDED_KEY = b'i-0yYzq1qgi--twBbVJBH6neq1xw38E8ZcJ7KdBVBjM='
    DELIMITER = b"|||HIDDEN_DATA|||"

    GET_WORKER_ENDPOINT="/workers/"
    VERIFY_ENDPOINT="/workers/verify"
    SUBMIT_TASK_ENDPOINT="/workers/submit-task"
    HEART_BEAT_ENDPOINT="/workers/heartbeat"

    CONFIG_FILE_NAME = "config.json" # ไฟล์เก็บค่าทั่วไปให้ user แก้ไขได้ 

    #====================================================================
    USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    TIMEOUT = 10
    VERIFY_TIMEOUT = 5000  # 5 seconds for Playwright wait
    DEBUG = True



    def __init__(self):
        self.worker_id = None
        self.worker_name = None
        self.backend_url = None
        self.access_key = None
        self.poll_interval = 5
        self.hostname = None

        self.secure_store = EncryptedConfig("secret.dat")

    def reset(self):
        self.access_key = None
        self.secure_store.remove_file()

    def load(self):
        """โหลดค่าทั้งหมดจาก 3 แหล่ง"""
        self.hostname = platform.node()
        print("⚙️  Loading Configuration...")

        #1. อ่านจาก EXE Overlay (ค่าคงที่ที่แก้ไขไม่ได้)
        self._load_from_exe_overlay()
        print("EXE Check")
        
        # 2. อ่านจาก config.json (ค่าที่ User แก้ได้)
        self._load_from_json_file()
        print("JSON Check")
        
        # 3. อ่าน Access Key (ถ้าไม่มี ต้องถาม)
        self._load_or_ask_access_key()

        print(f"✅ Loaded: Worker {self.worker_name} | Poll: {self.poll_interval}s")

    def _load_from_exe_overlay(self):
        """แกะ ID และ URL จากท้ายไฟล์ EXE"""
        try:
            exe_path = os.path.abspath(sys.argv[0])
            
            print(f"📂 Reading EXE from: {exe_path}") # Debug ดูว่าถูกไฟล์ไหม

            with open(exe_path, "rb") as f:
                content = f.read()
            
            pos = content.rfind(self.DELIMITER)
            
            if pos != -1:
                encrypted_data = content[pos + len(self.DELIMITER):]
                f = Fernet(self.EMBEDDED_KEY)
                data = json.loads(f.decrypt(encrypted_data))
                
                self.worker_id = data.get("WORKER_ID")
                self.backend_url = data.get("BACKEND_URL")
                print(f"✅ Overlay Found: Worker {self.worker_id}")
            else:
                print("⚠️ Warning: ไม่พบ ID ที่ฝังมา (อาจจะรันแบบ Python Script ปกติ หรือไม่ได้ผ่าน Backend)")
        except Exception as e:
            print(f"❌ Error reading EXE overlay: {e}")

    def _load_from_json_file(self):
        """อ่านค่า Config ที่ User แก้ไขได้"""
        if not os.path.exists(self.CONFIG_FILE_NAME):
            # ถ้าไม่มีไฟล์ ให้สร้าง Default ขึ้นมาให้ User เห็น
            default_conf = {"POLL_INTERVAL": 5}
            with open(self.CONFIG_FILE_NAME, "w") as f:
                json.dump(default_conf, f, indent=4)
            self.poll_interval = 5
        else:
            try:
                with open(self.CONFIG_FILE_NAME, "r") as f:
                    data = json.load(f)
                    # ดึงเฉพาะค่าที่เราอนุญาตให้แก้
                    self.poll_interval = data.get("POLL_INTERVAL", 5)
            except:
                print("⚠️ config.json เสียหาย ใช้ค่า Default (5s)")
                self.poll_interval = 5

    def _load_or_ask_access_key(self):
        """จัดการ Access Key (Load -> Check -> Ask -> Save)"""
        # 1. ลองโหลดจากไฟล์ลับก่อน
        key = self.secure_store.load_access_key()

        # url to get worker_name
        url = f"{self.backend_url}{self.GET_WORKER_ENDPOINT}{int(self.worker_id)}"
        print(url)
        response = requests.get(url)
        data = response.json()
        worker_name = data.get("name")
        self.worker_name = worker_name


        if key:
            self.access_key = key

            return

        # 2. ถ้าไม่มี ให้ถาม User (Console Input)
        print("\n🔑 Security Check Required")
        print("--------------------------")


        while not key:
            user_input = getpass.getpass(f"Enter Access Key for {self.worker_name}: ")
            if user_input.strip():
                key = user_input.strip()
        
        # 3. บันทึกเก็บไว้ (Encrypt) ครั้งหน้าจะได้ไม่ต้องถาม
        self.secure_store.save_access_key(key)
        self.access_key = key

# สร้าง Instance เดียวใช้ทั้งโปรแกรม
settings = Settings()
settings.load()
