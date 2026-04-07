# AGENT-CE68-22

1.
python -m nuitka --standalone --output-filename=Pest10Worker.exe --include-data-dir=./src/data=data --include-data-dir="Z:\Thesis\Code\AGENT-CE68-22\.venv\Lib\site-packages\playwright=playwright" --include-package=cryptography --include-package=charset_normalizer --include-package=requests --include-package=playwright main.py

2.
xcopy /E /I /Y "%USERPROFILE%\AppData\Local\ms-playwright\chromium-1200" "main.dist\playwright\driver\package\.local-browsers\chromium-1200"