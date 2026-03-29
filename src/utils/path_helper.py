import sys
import os

def get_resource_path(relative_path):
    """
    Resolve a path to a bundled resource.

    Priority:
      1. PyInstaller bundle  → sys._MEIPASS
      2. Frozen build (Nuitka / cx_Freeze)  → sys.frozen + dirname(executable)
      3. Development (normal Python)  → project root
         src/utils/path_helper.py → src/utils → src → <project_root>
    """
    if hasattr(sys, '_MEIPASS'):
        # PyInstaller: files extracted to a temp folder
        base_path = sys._MEIPASS
    elif getattr(sys, 'frozen', False):
        # Other frozen builds (Nuitka, cx_Freeze, etc.)
        base_path = os.path.dirname(sys.executable)
    else:
        # Development: walk up from src/utils/ → src/ → project_root/
        utils_dir = os.path.dirname(os.path.abspath(__file__))  # src/utils
        src_dir   = os.path.dirname(utils_dir)                  # src
        base_path = os.path.dirname(src_dir)                    # project root

    return os.path.join(base_path, relative_path)