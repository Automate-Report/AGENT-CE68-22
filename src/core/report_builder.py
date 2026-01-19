import time

class VulnerabilityBuilder:
    def __init__(self):
        # 1. Database ข้อมูลความรุนแรง (Severity)
        self.severity_map = {
            "Error-Based SQLi": "CRITICAL",
            "Boolean-Based SQLi": "CRITICAL",
            "Time-Based SQLi": "CRITICAL",
            "Reflected XSS": "MEDIUM",
            "DOM XSS": "MEDIUM",
            "Stored XSS": "HIGH"
        }

        # 2. Database คำอธิบายและวิธีแก้ (Knowledge Base)
        self.knowledge_base = {
            "SQLi": {
                "name": "SQL Injection",
                "desc": "The application allows an attacker to interfere with the queries that it makes to its database. This can lead to data theft, modification, or deletion.",
                "fix": "Use Prepared Statements (Parameterized Queries) for all database access. Validate and sanitize all user inputs."
            },
            "XSS": {
                "name": "Cross-Site Scripting (XSS)",
                "desc": "The application includes untrusted data in a web page without proper validation or escaping. This allows attackers to execute malicious scripts in the victim's browser.",
                "fix": "Context-sensitive encoding (Output Encoding) is the primary defense. For DOM XSS, avoid using dangerous sinks like innerHTML and use textContent instead."
            }
        }

    def build(self, url, param, vuln_type, payload, screenshot, **kwargs):
        """
        สร้าง Dictionary มาตรฐานสำหรับทุกช่องโหว่
        kwargs: รับค่าอื่นๆ เพิ่มเติม เช่น details, response_obj, db_type, context
        """
        
        # 1. ระบุ Group (เพื่อดึง Desc/Fix)
        vuln_group = "SQLi" if "SQLi" in vuln_type else "XSS"
        kb = self.knowledge_base.get(vuln_group, {})

        # 2. ดึงข้อมูลเสริมจาก kwargs
        details = kwargs.get("details", "")
        db_type = kwargs.get("db_type", "Unknown")
        context = kwargs.get("context", "General")
        response_obj = kwargs.get("response_obj", None)
        method = kwargs.get("method", "GET")

        # 3. ดึง Technical Info จาก Response Object (ถ้ามี)
        status_code = 0
        req_headers = ""
        res_headers = ""
        
        if response_obj:
            status_code = response_obj.status_code
            res_headers = str(dict(response_obj.headers))
            # Request headers อาจต้องดึงจาก response_obj.request.headers
            try: req_headers = str(dict(response_obj.request.headers))
            except: pass

        # 4. สร้าง cURL Command (เพื่อ Dev เอาไปเทสซ้ำ)
        curl_cmd = f"curl -X {method} '{url}?{param}={payload}'"
        if req_headers: 
             # (แบบย่อ) ของจริงอาจต้อง parse headers มาใส่ -H
             pass 

        # --- FINAL JSON STRUCTURE ---
        return {
            "target": {
                "url": url,
                "parameter": param,
                "method": method
            },
            "vulnerability": {
                "type": vuln_type,
                "severity": self.severity_map.get(vuln_type, "LOW"),
                "db_type": db_type if vuln_group == "SQLi" else None,
                "xss_context": context if vuln_group == "XSS" else None
            },
            "evidence": {
                "payload": payload,
                "details": details,  # Error msg หรือข้อความที่เจอ
                "screenshot": screenshot, # Base64 String
                "curl_command": curl_cmd
            },
            "technical": {
                "status_code": status_code,
                "request_headers": req_headers,
                "response_headers": res_headers,
                "timestamp": time.time()
            },
            "remediation": {
                "description": kb.get("desc", ""),
                "recommendation": kb.get("fix", "")
            }
        }