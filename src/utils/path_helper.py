import sys
import os

def get_resource_path(relative_path):
    """
    ฟังก์ชันนี้จะหา Path ที่ถูกต้องให้เอง
    - ถ้าเป็น Dev Mode: จะหาจากโฟลเดอร์โปรเจกต์
    - ถ้าเป็น EXE Mode: จะหาจากโฟลเดอร์ Temp ที่ EXE แตกไฟล์ออกมา (_MEIPASS)
    """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)