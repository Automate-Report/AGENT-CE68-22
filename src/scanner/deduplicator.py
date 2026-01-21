#ตัด url ที่ซ้ำ
class Deduplicator:
    def __init__(self):
        self.seen_urls = set()

    def is_seen(self, item: str) -> bool:
        return item in self.seen_urls

    def add(self, item: str):
        self.seen_urls.add(item)