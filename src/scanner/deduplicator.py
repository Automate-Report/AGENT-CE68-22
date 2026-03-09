import re
from urllib.parse import urlparse


class Deduplicator:
    def __init__(self):
        self.seen_signatures = set()

    def is_seen(self, method: str, url: str, params: dict) -> bool:
        parsed = urlparse(url)
        # Normalize: ตัด / ตัวสุดท้ายออก และทำให้เป็นตัวเล็กทั้งหมด
        path = parsed.path.rstrip('/').lower()
        if not path: path = "/"
        
        # จัดการ Fragment (Routing ของ SPA)
        fragment = parsed.fragment.split('?')[0].rstrip('/').lower()
        
        # จัดการ Params: เอาแค่ชื่อ Key มาเรียงกัน (ไม่เอาค่า เพื่อลดความซ้ำซ้อน)
        param_keys = sorted([str(k).lower() for k in params.keys()])
        # จัดการ Dynamic Mat-Input IDs
        clean_params = [re.sub(r'mat-input-\d+|input-\d+', 'input-id', k) for k in param_keys]
        param_str = ",".join(clean_params)

        signature = f"{method.upper()}|{parsed.netloc}{path}#{fragment}|{param_str}"
        
        if signature in self.seen_signatures:
            return True # "เคยเห็นแล้ว" -> คืนค่า True เพื่อให้ระบบข้ามไป
        
        self.seen_signatures.add(signature)
        return False # "ยังไม่เคยเห็น" -> คืนค่า False เพื่อให้ทำงานต่อ