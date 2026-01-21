import re

class ContextAnalyzer:
    def __init__(self):
        # Default probe base (คำหลักที่จะใช้หา)
        self.default_probe = "XSSPROBE"

    def _context_analyze(self, html_content: str, probe_string: str = None) -> list:
        """
        Service: ตรวจจับ probe_string ใน html_content ที่ได้จากการยิง request ใน scanner
        """
        contexts = []

        # Example <input type="text" name="user" value="HELLO_PROBE">
        if re.search(f'=["\'][^"\'<>]*{probe_string}', html_content, re.IGNORECASE):
            contexts.append("HTML_ATTRIBUTE")

        # JavaScript Context: <script>...PROBE...</script>
        # Example: <script>var x = "HELLO_PROBE";</script>
        if re.search(f'<script.*?>.*?{probe_string}.*?</script>', html_content, re.DOTALL | re.IGNORECASE):
            contexts.append("JAVASCRIPT_VAR")

        # HTML Body (Fallback), Element ใน html
        # Example: <div>Hello, HELLO_PROBE</div>
        if not contexts:
            contexts.append("HTML_BODY")

        return contexts
    
    def _bad_charecter_analyze(self, html_content: str, probe_string: str = None) -> dict:
        """
        Service: ตรวจสอบ html_content ที่ได้จาก server เรื่องอักขระพิเศษว่า server จัดการพวกนี้ยังไง
        สมมติเราส่ง: XSSPROBE"'> <
        Regex นี้จะจับสิ่งที่ตามหลัง XSSPROBE ออกมา
        """

        result = {
            "reflected_raw": None,
            "bad_chars": []
        }

        match = re.search(f"{re.escape(probe_string)}(.*?)", html_content, re.DOTALL | re.IGNORECASE)
        
        if match:
            # ดึงข้อความดิบๆ ที่ต่อท้ายมา (เช่น &quot;'> &lt;)
            reflected_suffix = match.group(1)
            # ตัดให้สั้นลงหน่อย (กันกรณีมันจับมายาวเกินไปจนจบบรรทัด) เอาแค่ 10-20 ตัวอักษรก็พอวิเคราะห์แล้ว
            reflected_suffix = reflected_suffix[:20] 
            
            result["reflected_raw"] = reflected_suffix

            # เช็คว่าตัวไหน "หายไป" หรือ "ถูกเปลี่ยน"
            # เราคาดหวังว่าถ้าไม่บล็อกเลย ต้องเจอ: " ' < >
            
            if '"' not in reflected_suffix:
                result["bad_chars"].append('"')  # Double Quote ใช้ไม่ได้
            
            if "'" not in reflected_suffix:
                result["bad_chars"].append("'")  # Single Quote ใช้ไม่ได้
            
            if "<" not in reflected_suffix:
                result["bad_chars"].append("<")  # Tag เปิด ใช้ไม่ได้ (อาจเป็น Body หรือ Attribute)
            
            if ">" not in reflected_suffix:
                result["bad_chars"].append(">")  # Tag ปิด ใช้ไม่ได้

        return result


    def analyze(self, html_content: str, probe_string: str = None) -> dict:
        """
        วิเคราะห์ HTML เพื่อหาตำแหน่งของ Probe และตรวจสอบ Bad Characters
        
        Args:
            html_content: HTML response จาก server
            probe_string: คำหลักที่ใช้ค้นหา (เช่น 'XSSPROBE') ไม่รวมอักขระพิเศษที่ต่อท้าย
        
        Returns:
            dict: {
                "contexts": [list of contexts],
                "bad_chars": [list of filtered chars],
                "reflected_raw": "raw string found after probe"
            }
        """
        result = {
            "contexts": [],
            "bad_chars": [],
            "reflected_raw": None
        }

        if not probe_string:
            probe_string = self.default_probe

        if not html_content or probe_string not in html_content:
            return result
        
        detected_contexts = self._context_analyze(html_content, probe_string)

        result["contexts"] = detected_contexts

        bad_char_result = self._bad_charecter_analyze(html_content, probe_string)

        result["reflected_raw"] = bad_char_result["reflected_raw"]
        result["bad_chars"] = bad_char_result["bad_chars"]

        return result