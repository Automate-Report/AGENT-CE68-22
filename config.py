import json
import os
import stat
import sys
from cryptography.fernet import Fernet

# --- Constants ---
SECRET_FILE = ".worker_secret"     # ไฟล์เก็บ Token (ห้ามแก้, ห้ามแชร์)
CONFIG_FILE = "worker_config.json" # ไฟล์ตั้งค่า (User แก้ได้)

# ค่า Default พื้นฐาน
DEFAULT_CONFIG = {
    "api_url": "http://localhost:8000",
    "task_interval_seconds": 60,
    "log_level": "INFO"
}

# from cryptography.fernet import Fernet
# print(Fernet.generate_key().decode())
# คุณจะได้ String ยาวๆ เช่น "Xj-9...=" ให้ Copy เก็บไว้

ENCRYPTION_KEY = b'gPN8qnR_vSIySogiV5QJBJcsWKoEBYBmebJPdy5rgSs=' 
cipher = Fernet(ENCRYPTION_KEY)

def get_app_path():
    """
    ฟังก์ชันหา Path ที่โปรแกรมรันอยู่จริง
    - ถ้ารันแบบ Script (.py) จะได้ path ของไฟล์นี้
    - ถ้ารันแบบ Frozen (.exe) จะได้ path ของไฟล์ .exe (ซึ่งเป็นที่ที่ไฟล์ config ควรอยู่)
    """
    if getattr(sys, 'frozen', False):
        # กรณีรันเป็น .exe (PyInstaller)
        return os.path.dirname(sys.executable)
    else:
        # กรณีรันเป็น .py
        return os.path.dirname(os.path.abspath(__file__))
    
APP_PATH = get_app_path()
SECRET_FILE_PATH = os.path.join(APP_PATH, "secret.dat")
CONFIG_FILE_PATH = os.path.join(APP_PATH, "config.dat")

def load_encrypted_json(filepath):
    """ฟังก์ชันช่วยอ่านไฟล์ที่เข้ารหัสไว้"""
    if not os.path.exists(filepath):
        return None
    try:
        with open(filepath, "rb") as f: # อ่านเป็น Bytes (rb)
            encrypted_data = f.read()
            
        # ถอดรหัส
        decrypted_data = cipher.decrypt(encrypted_data)
        
        # แปลง Bytes -> JSON Dict
        return json.loads(decrypted_data.decode())
    except Exception as e:
        print(f"Error loading {filepath}: {e}")
        return None


def load_settings():
    settings = {
        "api_url": "http://localhost:8000", # Default fallback
        "task_interval_seconds": 60
    }
    
    # 1. โหลด Config (ที่เข้ารหัสแล้ว)
    user_config = load_encrypted_json(CONFIG_FILE_PATH)
    if user_config:
        settings.update(user_config)

    # 2. โหลด Secret (ที่เข้ารหัสแล้ว)
    secrets = load_encrypted_json(SECRET_FILE_PATH)
    if secrets:
        settings["auth"] = secrets
    else:
        settings["auth"] = None

    return settings


def save_secret(data):
    """
    บันทึกข้อมูลความลับ (Token) ลงไฟล์ .worker_secret
    พร้อมตั้งค่า Permission ให้ปลอดภัย (chmod 600)
    """
    try:
        with open(SECRET_FILE, "w", encoding='utf-8') as f:
            json.dump(data, f, indent=4)
        
        # Security: จำกัดสิทธิ์การอ่านไฟล์
        if os.name == 'posix': # Linux/Mac
            os.chmod(SECRET_FILE, stat.S_IRUSR | stat.S_IWUSR)
        elif os.name == 'nt': # Windows
             os.chmod(SECRET_FILE, stat.S_IREAD | stat.S_IWRITE)
             
        print(f"[Config] Secret saved securely to {SECRET_FILE}")
    except Exception as e:
        print(f"[Config] Error saving secret: {e}")

