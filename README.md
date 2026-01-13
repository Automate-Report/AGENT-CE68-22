# AGENT-CE68-22
python -m nuitka --standalone --onefile --enable-plugin=anti-bloat --include-package=src main.py ไว้สร้าง exe
pyinstaller --onedir --name=SecurityWorker main.py exe + folder
python -m nuitka --enable-plugin=anti-bloat --include-package=src main.py
.venv\Scripts\Activate.ps1