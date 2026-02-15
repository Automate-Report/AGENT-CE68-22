import json

class SessionManager:
    def __init__(self):
        self.cookies = None
        self.local_storage = None

    def save_session(self, page):
        """ดึง Cookies และ LocalStorage เก็บไว้"""
        try:
            self.cookies = page.context.cookies()
            self.local_storage = page.evaluate("() => JSON.stringify(localStorage)")
        except: pass

    def apply_session(self, context, page=None):
        """แปะ Session กลับเข้าสู่ Context/Page ใหม่"""
        if self.cookies:
            context.add_cookies(self.cookies)
        
        if self.local_storage and page:
            try:
                # LocalStorage ต้องเขียนเข้าผ่านหน้าเว็บที่เปิดอยู่
                script = f"() => {{ const data = {self.local_storage}; for(let k in data) localStorage.setItem(k, data[k]); }}"
                page.evaluate(script)
            except: pass