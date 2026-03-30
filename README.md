# AGENT-CE68-22
python -m nuitka --standalone --onefile --enable-plugin=anti-bloat --include-package=src main.py ไว้สร้าง exe
pyinstaller --onedir --name=SecurityWorker main.py exe + folder
python -m nuitka --enable-plugin=anti-bloat --include-package=src main.py
.venv\Scripts\Activate.ps1

pyinstaller --onedir --name=Pest10Worker --add-data "./src/data;data" main.py

pyinstaller --onedir \
  --name=Pest10Worker \
  --add-data "./src/data;data" \
  --collect-all cryptography \
  --collect-all charset_normalizer \
  main.py

python -m nuitka --standalone --output-filename=Pest10Worker.exe --include-data-dir=./src/data=data --include-package=cryptography --include-package=charset_normalizer --include-package=requests main.py


1.
python -m nuitka --standalone --output-filename=Pest10Worker.exe --include-data-dir=./src/data=data --include-data-dir="Z:\Thesis\Code\AGENT-CE68-22\.venv\Lib\site-packages\playwright=playwright" --include-package=cryptography --include-package=charset_normalizer --include-package=requests --include-package=playwright main.py

2.
# Copy chromium browser into dist folder
xcopy /E /I /Y "%USERPROFILE%\AppData\Local\ms-playwright\chromium_headless_shell-1200" "main.dist\playwright\driver\package\.local-browsers\chromium_headless_shell-1200"