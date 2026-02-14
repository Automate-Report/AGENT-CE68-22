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
            "Stored XSS": "HIGH"
        }

        self.knowledge_base = {
            "SQLi": {
                "name": "SQL Injection",
                "desc": "The application allows an attacker to interfere with the queries it makes to its database.",
                "fix": "Use Prepared Statements (Parameterized Queries) and validate all user inputs."
            },
            "XSS": {
                "name": "Cross-Site Scripting (XSS)",
                "desc": "The application includes untrusted data in a web page without proper escaping, allowing script execution.",
                "fix": "Use context-sensitive output encoding and avoid dangerous DOM sinks like innerHTML."
            }
        }

    def build(self, url, param, vuln_type, payload, screenshot, **kwargs):
        vuln_group = "SQLi" if "SQLi" in vuln_type else "XSS"
        kb = self.knowledge_base.get(vuln_group, {})

        # ดึงข้อมูลเสริม
        method = kwargs.get("method", "GET").upper()
        content_type = kwargs.get("content_type", "form")
        response_obj = kwargs.get("response_obj", None)
        
        # ดึงค่าจาก Response (ถ้ามี)
        status_code = response_obj.status_code if response_obj else 0
        res_headers = dict(response_obj.headers) if response_obj else {}
        req_headers = dict(response_obj.request.headers) if response_obj and hasattr(response_obj.request, 'headers') else {}

        # --- สร้าง cURL Command ที่ใช้งานได้จริง ---
        curl_cmd = self._generate_curl(url, method, param, payload, content_type)

        # --- จัดทำโครงสร้างข้อมูลตามที่ต้องการ ---
        return {
            "target": {
                "url": url,
                "parameter": param,
                "method": method,
                "content_type": content_type
            },
            "vulnerability": {
                "type": vuln_type,
                "severity": self.severity_map.get(vuln_type, "LOW"),
                "db_type": kwargs.get("db_type") if vuln_group == "SQLi" else None,
                "xss_context": kwargs.get("context") if vuln_group == "XSS" else None
            },
            "evidence": {
                "payload": payload,
                "details": kwargs.get("details", ""),
                "screenshot": screenshot, # Base64 String
                "curl_command": curl_cmd
            },
            "technical": {
                "status_code": status_code,
                "request_headers": req_headers,
                "response_headers": res_headers,
                "timestamp": int(time.time())
            },
            "remediation": {
                "description": kb.get("desc", ""),
                "recommendation": kb.get("fix", "")
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