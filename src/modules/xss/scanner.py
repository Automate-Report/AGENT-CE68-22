# Logic หลัก Analyze -> Payload -> Verify
# security-worker/modules/xss/scanner.py

from src.modules.base_module import BaseScanner
from src.modules.xss.context import ContextAnalyzer
from src.modules.xss.verifier import XSSVerifier

from src.core.requester import Requester
from src.core.logger import setup_logger
from src.core.report_builder import VulnerabilityBuilder

from src.utils.load_file import load_file
from src.utils.path_helper import get_resource_path

class XSSScanner(BaseScanner):
    def __init__(self):
        super().__init__()
        self.name = "XSS Scanner Module"
        self.requester = Requester()
        self.analyzer = ContextAnalyzer()
        self.verifier = XSSVerifier()
        self.logger = setup_logger("XSSScanner")
        self.report_builder = VulnerabilityBuilder()
        
        # จำลอง Payload (ของจริงควรโหลดจากไฟล์)
        self.payloads = {
            "HTML_BODY": load_file(get_resource_path('data/payloads/xss/body.txt'), self.logger),
            "HTML_ATTRIBUTE": load_file(get_resource_path('data/payloads/xss/attribute.txt'), self.logger),
            "JAVASCRIPT_VAR": load_file(get_resource_path('data/payloads/xss/script.txt'), self.logger),
            "GENERIC": load_file(get_resource_path('data/payloads/xss/polyglot.txt'), self.logger)
        }

    def scan(self, url: str, params: dict) -> list:
        """
        Main Logic Scan
        """
        findings = []
        self.logger.info(f"[*] XSS Scanning: {url}")

        for param_key, original_value in params.items():
            self.logger.info(f"    -> Analyzing parameter: {param_key}")

            # 1. Step 1: วิเคราะห์บริบท (Probing)
            analysis_result = self._analyze_parameter(url, param_key, params)
            
            if not analysis_result["found"]:
                self.logger.info(f"        [-] No reflection found for {param_key}")
                continue

            # 2. Step 2: เลือก Payload (Strategy)
            target_payloads = self._select_payloads(analysis_result)

            self.logger.info(f"    [*] Injection Phase: Testing {len(target_payloads)} payloads...")

            # 3. Step 3: โจมตีและตรวจสอบ (Attack & Verify)
            vulnerability = self._execute_attack(url, param_key, params, target_payloads, analysis_result["contexts"])
            
            if vulnerability:
                findings.append(vulnerability)

                break

        return findings


    def _analyze_parameter(self, url: str, param_key: str, original_params: dict) -> dict:
        """
        Service: ยิง Probe เพื่อหา Context และ Bad Chars (Mixed -> Clean Fallback)
        """
        # เตรียมตัวแปรผลลัพธ์
        result = {
            "found": False,
            "contexts": [],
            "bad_chars": [],
            "reflected_raw": None
        }

        # --- 1.1 Try Mixed Probe (ของหนัก) ---
        mixed_payload = self.analyzer.default_probe + "\"'><"
        probe_params = original_params.copy()
        probe_params[param_key] = mixed_payload
        
        self.logger.info(f"    [>] Trying Mixed Probe: {mixed_payload}")
        try:
            response = self.requester.get(url, params=probe_params)
        except Exception as e:
            self.logger.error(f"    [-] Request failed: {e}")
            return result

        if self.analyzer.default_probe in response.text:
            self.logger.info(f"        [+] Found Reflection with Mixed Probe!")
            analysis = self.analyzer.analyze(response.text, self.analyzer.default_probe)
            
            result["found"] = True
            result["contexts"] = analysis["contexts"]
            result["bad_chars"] = analysis["bad_chars"]
            result["reflected_raw"] = analysis["reflected_raw"]
            
            self.logger.info(f"        [+] Context: {result['contexts']}")
            self.logger.info(f"        [+] Bad Chars: {result['bad_chars']}")

            self.logger.debug(f"        [DEBUG] Reflected Raw Suffix: '{result['reflected_raw']}'")
                
            # +++ เพิ่มบรรทัดนี้เพื่อดูเนื้อหาจริงๆ รอบๆ Probe +++
            start_index = response.text.find(self.analyzer.default_probe)
            # ตัดข้อความมาดู หน้า 10 ตัว หลัง 20 ตัว
            snippet = response.text[max(0, start_index-10) : start_index+30]
            self.logger.debug(f"        [DEBUG] Full Snippet from Server: ...{snippet}...")
            return result

        # --- 1.2 Try Clean Probe (ของเบา - Fallback) ---
        self.logger.info(f"        [-] Mixed Probe failed. Retrying with Clean Probe...")
        probe_params[param_key] = self.analyzer.default_probe
        response = self.requester.get(url, params=probe_params)

        if self.analyzer.default_probe in response.text:
            self.logger.info(f"        [+] Found Reflection with Clean Probe!")
            analysis = self.analyzer.analyze(response.text, self.analyzer.default_probe)
            
            result["found"] = True
            result["contexts"] = analysis["contexts"]
            result["bad_chars"] = [] # ไม่รู้ Bad Chars แต่รู้ว่า Reflect
            result["reflected_raw"] = analysis["reflected_raw"]

            self.logger.info(f"        [+] Context: {result['contexts']}")
            self.logger.warning(f"        [!] Warning: Special characters caused instability.")
            return result

        return result

    def _select_payloads(self, analysis_result: dict) -> list:
        """
        Service: เลือกและกรอง Payload ตาม Context และ Bad Chars
        """
        contexts = analysis_result["contexts"]
        bad_chars = analysis_result["bad_chars"]
        selected_payloads = []

        # ดึง Payload ตาม Context
        for ctx in contexts:
            raw_payloads = self.payloads.get(ctx, [])
            
            # กรอง Payload ที่มี Bad Chars
            if bad_chars:
                valid_payloads = [
                    p for p in raw_payloads 
                    if not any(bc in p for bc in bad_chars)
                ]
                selected_payloads.extend(valid_payloads)
            else:
                selected_payloads.extend(raw_payloads)
            # selected_payloads.extend(raw_payloads)

        # Fallback ถ้าไม่มี Payload หรือโดนกรองหมด
        if not selected_payloads:
            selected_payloads = self.payloads.get("GENERIC", [])
            
        return selected_payloads

    def _execute_attack(self, url: str, param_key: str, original_params: dict, payloads: list, contexts: list):
        """
        Service: ยิง Payload จริง และตรวจสอบผลลัพธ์ (Verify ด้วย Browser)
        """
        for payload in payloads:
            attack_params = original_params.copy()
            attack_params[param_key] = payload
            
            try:
                # 1. ยิง Request ผ่าน Requester เดิม
                response = self.requester.get(url, params=attack_params)
            except Exception as e:
                self.logger.error(f"       [-] Attack request failed: {e}")
                continue

            # 2. Passive Check: ดู Source Code ก่อน (เร็ว)
            if payload in response.text:
                self.logger.info(f"       [?] Potential found in Source Code. Verifying with Browser...")
                
                # 3. Active Verification: เอา URL จริงจาก response ส่งไปให้ Playwright (ช้าแต่ชัวร์)
                # response.url คือ URL เต็มๆ ที่ถูก encode params เรียบร้อยแล้ว
                verify_result = self.verifier.verify(response.url)
                
                if verify_result:
                    self.logger.info(f"       [!!!] CONFIRMED VULNERABILITY! (Alert Popped)")
                    self.logger.info(f"             Payload: {payload}")

                    finding = self.report_builder.build(
                        url=url,
                        param=param_key,
                        vuln_type="Reflected XSS",
                        payload=payload,
                        screenshot=verify_result["screenshot"], # รับรูปจาก Verifier
                        
                        # ข้อมูลเสริม
                        details=f"Payload reflected in contexts: {contexts}",
                        context=contexts[0] if contexts else "Unknown",
                        response_obj=response, # ส่ง response object ไปดึง headers/status code
                        method="GET"
                    )
                    
                    return finding
                else:
                    self.logger.info(f"       [-] Verification Failed. Payload in source but script didn't run.")
        
        return None