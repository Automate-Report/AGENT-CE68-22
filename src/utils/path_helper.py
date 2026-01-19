import sys
import os

def get_resource_path(relative_path):
    """
    หา Path ที่ถูกต้อง รองรับทั้ง Dev Mode (รันด้วย Python) และ EXE Mode (PyInstaller)
    """
    if getattr(sys, 'frozen', False):
        # --- กรณี EXE Mode ---
        # หาจากโฟลเดอร์ Temp ที่ EXE แตกไฟล์ออกมา
        base_path = sys._MEIPASS
    else:
        # --- กรณี Dev Mode ---
        # หาจากที่อยู่ของไฟล์นี้ (path_helper.py) แล้วถอยกลับไปหา Root Project
        # สมมติไฟล์นี้อยู่ Z:\Thesis\...\utils\path_helper.py
        
        # 1. หา path ของไฟล์นี้
        current_file_path = os.path.abspath(__file__)
        
        # 2. ถอยออกมา 1 ขั้น (ได้โฟลเดอร์ utils)
        utils_dir = os.path.dirname(current_file_path)
        
        # 3. ถอยอีก 1 ขั้น (ได้โฟลเดอร์โปรเจกต์หลัก AGENT-CE68-22)
        base_path = os.path.dirname(utils_dir)

    return os.path.join(base_path, relative_path)