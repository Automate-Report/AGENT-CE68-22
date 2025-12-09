import json
import os
import stat
import sys

# --- Constants ---
SECRET_FILE = ".worker_secret"     # ไฟล์เก็บ Token (ห้ามแก้, ห้ามแชร์)
CONFIG_FILE = "worker_config.json" # ไฟล์ตั้งค่า (User แก้ได้)

# ค่า Default พื้นฐาน
DEFAULT_CONFIG = {
    "api_url": "http://localhost:8000",
    "task_interval_seconds": 60,
    "log_level": "INFO"
}

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
SECRET_FILE_PATH = os.path.join(APP_PATH, ".worker_secret")
CONFIG_FILE_PATH = os.path.join(APP_PATH, "worker_config.json")

def load_settings():
    """
    โหลด Config ทั้งหมด (Default + User Config + Secret)
    คืนค่าเป็น Dictionary เดียว
    """
    # 1. เริ่มจากค่า Default
    settings = DEFAULT_CONFIG.copy()
    
    # 2. โหลด User Config (ถ้ามี) มาทับค่า Default
    if os.path.exists(CONFIG_FILE_PATH):
        try:
            with open(CONFIG_FILE_PATH, "r", encoding='utf-8') as f:
                user_config = json.load(f)
                settings.update(user_config)
        except Exception as e:
            print(f"[Config] Warning: Could not read {CONFIG_FILE}: {e}")

    # 3. โหลด Secret (ถ้ามี) มาเก็บใน key 'auth'
    if os.path.exists(SECRET_FILE_PATH):
        try:
            with open(SECRET_FILE_PATH, "r", encoding='utf-8') as f:
                secrets = json.load(f)
                settings["auth"] = secrets
        except Exception as e:
            print(f"[Config] Warning: Could not read {SECRET_FILE}: {e}")
            settings["auth"] = None
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

