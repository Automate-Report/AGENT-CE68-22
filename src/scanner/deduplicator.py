import re
from urllib.parse import urlparse


class Deduplicator:
    def __init__(self):
        self.seen_signatures = set()
        self.seen_pii_endpoints = set()

    def is_seen(self, method: str, url: str, params: dict) -> bool:
        # 1. Normalize URL: ตัด query string ออกและจัดการ trailing slash
        parsed = urlparse(url)
        path = parsed.path.rstrip('/')
        if not path: path = "/"
        
        # 2. Handle Angular/Material Dynamic IDs (Fuzzy Match)
        # เปลี่ยน 'mat-input-123' ให้เป็น 'mat-input-ID' เพื่อลดความซ้ำซ้อน
        clean_params = []
        for k in sorted(params.keys()):
            k_normalized = re.sub(r'mat-input-\d+', 'mat-input-ID', k)
            clean_params.append(k_normalized)
        
        param_str = ",".join(clean_params)

        # 3. Create Signature
        signature = f"{method.upper()}|{parsed.netloc}{path}|{param_str}"
        
        if signature in self.seen_signatures:
            return True
        
        self.seen_signatures.add(signature)
        return False

    def is_pii_reported(self, url: str) -> bool:
        """Helper ใหม่: เช็คว่า Endpoint นี้เคยเตือน PII ไปหรือยัง"""
        path = urlparse(url).path.rstrip('/')
        if path in self.seen_pii_endpoints:
            return True
        self.seen_pii_endpoints.add(path)
        return False