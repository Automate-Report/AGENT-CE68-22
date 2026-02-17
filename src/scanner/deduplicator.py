#ตัด url ที่ซ้ำ
class Deduplicator:
    def __init__(self):
        self.seen_urls = set()

    def is_seen(self, method: str, url_path: str, params: dict) -> bool:
        param_keys = ",".join(sorted(params.keys()))

        signature = f"{method}|{url_path}|{param_keys}"
        if signature in self.seen_signatures:
            return True
        self.seen_signatures.add(signature)
        return False

    def add(self, item: str):
        self.seen_urls.add(item)