import re
from urllib.parse import urlparse

class Deduplicator:
    def __init__(self):
        self.seen_signatures = set()

    def is_seen(self, method: str, url: str, params: dict) -> bool:
        parsed = urlparse(url)
        
        # 1. Normalize Path และจัดการ Path Parameters (REST API Identification)
        # เช่น /api/v1/user/123/profile -> /api/v1/user/{id}/profile
        path_parts = parsed.path.rstrip('/').split('/')
        clean_path_parts = []
        for part in path_parts:
            # ถ้า part เป็นตัวเลขล้วน หรือเป็น UUID/Hash ให้ยุบเป็น {id}
            if part.isdigit() or re.match(r'^[a-f0-9-]{32,36}$', part.lower()):
                clean_path_parts.append("{id}")
            else:
                clean_path_parts.append(part.lower())
        
        clean_path = "/".join(clean_path_parts)
        if not clean_path: clean_path = "/"
        
        # 2. จัดการ Fragment (Routing ของ SPA)
        # เช่น /#/user/edit/1 -> /#/user/edit/{id}
        fragment_raw = parsed.fragment.split('?')[0].rstrip('/')
        frag_parts = fragment_raw.split('/')
        clean_frag_parts = [
            "{id}" if p.isdigit() or re.match(r'^[a-f0-9-]{32,36}$', p.lower()) else p.lower() 
            for p in frag_parts
        ]
        clean_fragment = "/".join(clean_frag_parts)

        # 3. จัดการ Params: กรอง Dynamic Mat-Input IDs และเรียง Key
        # เราไม่เอา Value มาคิด เพื่อลดความซ้ำซ้อนในการแสกนโครงสร้างเดิม
        param_keys = sorted([str(k).lower() for k in params.keys()])
        
        # ยุบพวก mat-input-123 หรือ auto-generated id ต่างๆ
        clean_params = [
            re.sub(r'(mat-input-|input-|field-)\d+', 'dynamic-id', k) 
            for k in param_keys
        ]
        param_str = ",".join(clean_params)

        # 4. สร้าง Unique Signature
        # โครงสร้าง: METHOD | DOMAIN/CLEAN_PATH # CLEAN_FRAGMENT | PARAM_KEYS
        signature = f"{method.upper()}|{parsed.netloc}{clean_path}#{clean_fragment}|{param_str}"
        
        if signature in self.seen_signatures:
            # self.logger.debug(f" [Deduplicator] Skip seen: {signature}") # ปลดคอมเมนต์ถ้าอยาก debug
            return True 
        
        self.seen_signatures.add(signature)
        return False