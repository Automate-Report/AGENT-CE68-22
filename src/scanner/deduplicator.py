import re
from urllib.parse import urlparse


class Deduplicator:
    def __init__(self):
        self.seen_signatures = set()

    def is_seen(self, method: str, url: str, params: dict) -> bool:
        parsed = urlparse(url)
        # แก้ตรงนี้: รวม fragment (#) เข้าไปด้วย เพราะ SPA ใช้แบ่งหน้า
        path = parsed.path.rstrip('/')
        fragment = parsed.fragment.split('?')[0] # เอาแค่ชื่อ route ไม่เอา query ใน fragment
        
        # จัดการ Dynamic IDs เหมือนเดิม
        clean_params = []
        for k in sorted(params.keys()):
            k_normalized = re.sub(r'mat-input-\d+|input-\d+', 'input-ID', k)
            clean_params.append(k_normalized)
        
        param_str = ",".join(clean_params)

        # Signature ใหม่ที่รองรับ SPA
        signature = f"{method.upper()}|{parsed.netloc}{path}#{fragment}|{param_str}"
        
        if signature in self.seen_signatures:
            return False # ส่ง False เพื่อบอกว่า "ไม่เห็นของใหม่" (คือข้ามไป)
        
        self.seen_signatures.add(signature)
        return True # ส่ง True เพื่อบอกว่า "นี่คือของใหม่ ให้เก็บซะ"