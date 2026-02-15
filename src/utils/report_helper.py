import base64

def capture_screenshot_base64(page) -> str:
    """ถ่ายรูปหน้าจอและแปลงเป็น Base64 String"""
    try:
        screenshot_bytes = page.screenshot(type="jpeg", quality=70)
        return base64.b64encode(screenshot_bytes).decode('utf-8')
    except:
        return ""

def add_vuln_overlay(page, message: str):
    """ฉีด JavaScript เพื่อสร้างแถบแจ้งเตือนช่องโหว่บนหน้าจอ (สำหรับทำหลักฐาน)"""
    script = f"""
    () => {{
        const div = document.createElement('div');
        div.style = "position:fixed;top:0;left:0;width:100%;background:rgba(255,0,0,0.9);color:white;z-index:999999;text-align:center;padding:15px;font-family:sans-serif;font-weight:bold;font-size:18px;";
        div.innerText = "🚨 {message}";
        document.body.appendChild(div);
    }}
    """
    try:
        page.evaluate(script)
    except: pass