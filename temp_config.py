import json
import os
import stat
import sys
from cryptography.fernet import Fernet

# --- Constants ---
SECRET_FILE = ".worker_secret"     # ไฟล์เก็บ Token (ห้ามแก้, ห้ามแชร์)
CONFIG_FILE = "worker_config.json" # ไฟล์ตั้งค่า (User แก้ได้)
KEY_FILE_PATH = ".system_lock"

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
SECRET_FILE_PATH = os.path.join(APP_PATH, "secret.dat")
CONFIG_FILE_PATH = os.path.join(APP_PATH, "config.dat")
KEY_FILE_PATH = os.path.join(APP_PATH, ".system_lock")


def load_key():
    """อ่านกุญแจจากไฟล์ .system_lock"""
    if not os.path.exists(KEY_FILE_PATH):
        print("Error: Encryption key not found!")
        return None
    try:
        with open(KEY_FILE_PATH, "rb") as f:
            return f.read().strip() # อ่านกุญแจออกมา
    except Exception as e:
        print(f"Error reading key: {e}")
        return None

def load_encrypted_json(filepath, cipher):
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

def save_secret(data):
    """บันทึกข้อมูลลับทับลงไปใหม่ (เช่น ตอนได้ API Key มาแล้ว)"""
    key = load_key()
    if not key:
        print("Error: No encryption key found, cannot save secret.")
        return

    try:
        cipher = Fernet(key)
        # แปลง Dict -> String -> Encrypted Bytes
        encrypted_data = cipher.encrypt(json.dumps(data).encode())
        
        with open(SECRET_FILE, "wb") as f:
            f.write(encrypted_data)
        print("✅ Secret updated successfully.")
    except Exception as e:
        print(f"Error saving secret: {e}")


def load_settings():
    settings = {
        "api_url": "http://localhost:8000",
        "task_interval_seconds": 60,
        "auth": {}
    }
    
    # 1. โหลดกุญแจก่อน
    key = load_key()
    if not key:
        print("⚠️ Warning: Encryption key not found. Agent might be unconfigured.")
        return settings

    # สร้าง Cipher จากกุญแจที่อ่านได้
    cipher = Fernet(key)

    # 2. โหลด Config & Secret (ส่ง cipher เข้าไป)
    user_config = load_encrypted_json(CONFIG_FILE_PATH, cipher)
    if user_config:
        settings.update(user_config)

    secrets = load_encrypted_json(SECRET_FILE_PATH, cipher)
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

