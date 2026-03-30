import time
import json

class VulnerabilityBuilder:
    def __init__(self):
        self.severity_map = {
            "Error-Based SQLi": "CRITICAL",
            "Boolean-Based SQLi": "CRITICAL",
            "Time-Based SQLi": "CRITICAL",
            "Reflected XSS": "MEDIUM",
            "DOM XSS": "MEDIUM",
            "Stored XSS": "HIGH",
            "Authentication Bypass via SQL Injection": "CRITICAL",
            "Insecure Direct Object Reference (IDOR)": "HIGH"
        }

        self.knowledge_base = {
            "Authentication Bypass via SQL Injection": {
                "name": "Authentication Bypass via SQL Injection",
                "desc": "ช่องโหว่ที่เกิดขึ้นเมื่อแอปพลิเคชันนำข้อมูลจากผู้ใช้ไปรวมใน Query สำหรับตรวจสอบสิทธิ์ (Authentication) โดยไม่มีการตรวจสอบที่ดีพอ ทำให้ผู้โจมตีสามารถข้ามขั้นตอนการเข้าสู่ระบบได้โดยไม่ต้องมีรหัสผ่านที่ถูกต้อง",
                "fix": "1. ใช้ Prepared Statements หรือ Parameterized Queries ในการจัดการข้อมูลจากผู้ใช้\n2. หลีกเลี่ยงการสร้าง Dynamic SQL String ในฟังก์ชัน Login\n3. ใช้ Library สำหรับ Authentication มาตรฐานแทนการเขียนระบบตรวจสอบเอง",
                "cvss_score": 9.8,
                "cvss_vector": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H"
            },
            "SQLi": {
                "name": "SQL Injection",
                "desc": "The application allows an attacker to interfere with the queries it makes to its database.",
                "fix": "Use Prepared Statements (Parameterized Queries) and validate all user inputs."
            },
            "XSS": {
                "name": "Cross-Site Scripting (XSS)",
                "desc": "The application includes untrusted data in a web page without proper escaping, allowing script execution.",
                "fix": "Use context-sensitive output encoding and avoid dangerous DOM sinks like innerHTML."
            },
            "IDOR": {
                "name": "Insecure Direct Object Reference (IDOR) / BOLA",
                "desc": "The application exposes direct references to private objects (like database IDs) and fails to verify if the requesting user has the appropriate permissions to access them.",
                "fix": "Implement robust access controls at the object level. Ensure that for every data access, the system verifies that the logged-in user is authorized to perform the action on the requested object."
            }
        }

    def build(self, url, param, vuln_type, payload, screenshot, **kwargs):
        if "SQL" in vuln_type: vuln_group = "SQLi"
        elif "XSS" in vuln_type: vuln_group = "XSS"
        else: vuln_group = "IDOR"

        # พยายามดึงคำอธิบายที่ตรงตัวเป๊ะๆ ก่อน ถ้าไม่มีถึงจะดึงแบบ Group (SQLi, XSS, IDOR)
        kb = self.knowledge_base.get(vuln_type) or self.knowledge_base.get(vuln_group, {})

        # --- แก้ไขจุดที่ 1: ดึงเฉพาะค่าดิบออกมา และบังคับเป็น String/Int เสมอ ---
        # การครอบด้วย str() จะช่วยล้าง Object ที่อาจหลงเหลืออยู่ในตัวแปร method หรือ url
        method = str(kwargs.get("method", "GET")).upper()
        content_type = str(kwargs.get("content_type", "form"))
        url = str(url)
        param = str(param)
        payload = str(payload)
        
        # --- แก้ไขจุดที่ 2: ดึงข้อมูลจาก Response แบบระมัดระวัง ---
        response_obj = kwargs.get("response_obj", None)
        status_code = 0
        res_headers = ""
        req_headers = ""

        if response_obj:
            status_code = int(response_obj.status_code)
            try:
                # ✅ แปลง Dict ให้เป็น JSON String เพื่อให้ตรงกับ Backend Schema (str)
                res_headers_dict = {str(k): str(v) for k, v in response_obj.headers.items()}
                res_headers = json.dumps(res_headers_dict) 

                if hasattr(response_obj, 'request') and hasattr(response_obj.request, 'headers'):
                    req_headers_dict = {str(k): str(v) for k, v in response_obj.request.headers.items()}
                    req_headers = json.dumps(req_headers_dict)
            except Exception:
                res_headers = "{}"
                req_headers = "{}"

        # สร้าง cURL Command (ส่งค่าที่เป็น string เข้าไป)
        curl_cmd = self._generate_curl(url, method, param, payload, content_type)

        # --- แก้ไขจุดที่ 3: จัดโครงสร้างโดยไม่มี Object ใดๆ หลงเหลือ ---
        return {
            "target": {
                "url": url,
                "parameter": param,
                "method": method,
                "content_type": content_type
            },
            "vulnerability": {
                "type": str(vuln_type),
                "severity": self.severity_map.get(vuln_type, "LOW"),
                "db_type": str(kwargs.get("db_type", "Unknown")) if vuln_group == "SQLi" else None,
                "xss_context": str(kwargs.get("context", "General")) if vuln_group == "XSS" else None
            },
            "evidence": {
                "payload": payload,
                "details": str(kwargs.get("details", "")),
                "screenshot": screenshot, # Base64 มักเป็น string อยู่แล้ว
                "curl_command": str(curl_cmd)
            },
            "technical": {
                "status_code": status_code,
                "request_headers": req_headers,
                "response_headers": res_headers,
                "timestamp": float(time.time())
            },
            "remediation": {
                "description": str(kb.get("desc", "")),
                "recommendation": str(kb.get("fix", ""))
            }
        }

    def _generate_curl(self, url, method, param, payload, content_type):
        """สร้าง cURL command ตาม Method และ Content-Type"""
        if method == "GET":
            return f"curl -X GET '{url}?{param}={payload}'"
        
        elif method == "POST":
            if content_type == "json":
                data = json.dumps({param: payload})
                return f"curl -X POST '{url}' -H 'Content-Type: application/json' -d '{data}'"
            else:
                return f"curl -X POST '{url}' -d '{param}={payload}'"
        
        return f"curl -X {method} '{url}'"