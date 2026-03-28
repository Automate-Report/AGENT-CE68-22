import sys
import os

def get_resource_path(relative_path):
    # ถ้า exe อยู่ใน main.dist → ใช้ dirname ของ executable
    if hasattr(sys, '_MEIPASS'):
        base_path = sys._MEIPASS
    elif os.path.basename(sys.executable).endswith('.exe'):
        base_path = os.path.dirname(sys.executable)
    else:
        current_file_path = os.path.abspath(__file__)
        utils_dir = os.path.dirname(current_file_path)
        base_path = os.path.dirname(utils_dir)

    return os.path.join(base_path, relative_path)