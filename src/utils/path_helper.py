import sys
import os

def get_resource_path(relative_path):
    """
    ฟังก์ชันมหัศจรรย์: หา Path ที่ถูกต้องไม่ว่าจะรันผ่าน Python หรือ EXE
    """
    if getattr(sys, 'frozen', False):
        # กรณีรันผ่าน EXE: ให้ใช้ Path ที่ไฟล์ .exe ตั้งอยู่
        base_path = os.path.dirname(sys.executable)
    else:
        # กรณีรันผ่าน Python ปกติ: ให้ใช้ Path ปัจจุบันของโปรเจกต์
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)