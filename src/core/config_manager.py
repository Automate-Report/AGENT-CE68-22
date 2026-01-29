import os
import json
import uuid
import base64

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from src.core.logger import setup_logger

class EncryptedConfig:
    def __init__(self, filename="worker_config.dat"):
        self.filename = filename
        self.key = self._generate_machine_key()
        self.logger = setup_logger("EncryptedConfig")

    def _generate_machine_key(self):
        """
        สร้าง Key สำหรับเข้ารหัสไฟล์ โดยอิงจาก Hardware ของเครื่อง (MAC Address)
        ทำให้ไฟล์ Config นี้ Copy ไปใช้เครื่องอื่นไม่ได้
        """
        # 1. ดึงค่า Unique ของเครื่อง (Mac Address)
        machine_id = str(uuid.getnode()).encode()
        
        # 2. แปลงให้เป็น Format ที่ Fernet รับได้ (32 bytes base64)
        salt = b'JimGiFbXqlAwUAXu2PM1' # เปลี่ยนค่านี้ให้เป็นความลับของคุณเอง
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        return base64.urlsafe_b64encode(kdf.derive(machine_id))

    def save_access_key(self, access_key: str):
        """รับ Key จาก user แล้วเข้ารหัสลงไฟล์"""
        fernet = Fernet(self.key)
        data = json.dumps({"access_key": access_key}).encode()
        encrypted_data = fernet.encrypt(data)
        
        with open(self.filename, "wb") as f:
            f.write(encrypted_data)
        
        self.logger.info(f"[Config] บันทึก Config แบบเข้ารหัสเรียบร้อยที่ {self.filename}")

    def load_access_key(self):
        """อ่านไฟล์และถอดรหัส"""
        if not os.path.exists(self.filename):
            return None
            
        try:
            with open(self.filename, "rb") as f:
                encrypted_data = f.read()
            
            fernet = Fernet(self.key)
            decrypted_data = fernet.decrypt(encrypted_data)
            config = json.loads(decrypted_data)
            return config.get("access_key")
        except Exception as e:
            self.logger.error("[Config] อ่าน Config ไม่ได้ (ไฟล์อาจถูกย้ายมาจากเครื่องอื่น หรือเสียหาย)")
            return None
    
    def remove_file(self):
        os.remove(self.filename)
