from urllib.parse import urlparse, urljoin

def is_internal_url(url: str, allowed_domain: str, blacklist: list) -> bool:
    """เช็คว่า URL อยู่ในขอบเขตที่กำหนดและไม่อยู่ใน Blacklist หรือไม่"""
    try:
        parsed = urlparse(url)
        # ตรวจสอบ Domain และ Port (ต้องตรงกัน)
        is_internal = parsed.netloc == allowed_domain
        # ตรวจสอบ Blacklist (เช่น facebook, youtube)
        is_blacklisted = any(domain in parsed.netloc.lower() for domain in blacklist)
        return is_internal and not is_blacklisted
    except:
        return False

def normalize_url(url: str) -> str:
    """ทำความสะอาด URL เพื่อใช้ทำ Signature (ตัด query/fragment)"""
    return url.split('?')[0].split('#')[0].rstrip('/')

def is_static_resource(url: str) -> bool:
    """เช็คว่าเป็นไฟล์ Static ที่ไม่ควรสแกนหรือไม่"""
    static_ext = ('.jpg', '.jpeg', '.png', '.gif', '.css', '.js', '.woff', '.woff2', '.pdf', '.svg', '.zip')
    return url.lower().endswith(static_ext)

def get_spa_path(url: str) -> str:
    """ดึง Path ของ SPA (รวมส่วนหลัง /#/)"""
    parsed = urlparse(url)
    if '#' in url:
        return parsed.path + '#' + parsed.fragment
    return parsed.path