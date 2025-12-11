import time
import requests
import platform
from datetime import datetime

# Import module config ที่เราเพิ่งสร้าง
import config 

current_jwt = None

def handshake(settings):
    """
    ใช้ Registration Token แลก API Key ถาวร
    """
    auth = settings.get("auth", {})
    reg_token = auth.get("registration_token")
    worker_id = auth.get("worker_id")
    api_url = settings.get("api_url")

    print(f"🚀 Initializing Handshake for Worker ID: {worker_id}...")

    try:
        # ยิงไปที่ Endpoint Handshake
        response = requests.post(f"{api_url}/workers/handshake", json={
            "registration_token": reg_token,
            "hostname": platform.node() # ส่งชื่อเครื่องไปด้วย
        })

        if response.status_code == 200:
            data = response.json()
            new_api_key = data["api_key"]

            # อัปเดตข้อมูลใหม่: มี API Key แล้ว, ลบ Token เก่าทิ้ง
            new_secret = {
                "worker_id": worker_id,     # ID เดิม
                "api_key": new_api_key,     # Key ใหม่
                "registration_token": None  # ลบทิ้ง
            }

            # บันทึกลงไฟล์ (Encrypted)
            config.save_secret(new_secret)
            
            # อัปเดตตัวแปร settings ในหน่วยความจำด้วย
            settings["auth"] = new_secret
            
            print(f"✅ Handshake Success! API Key obtained.")
            return True
        elif response.status_code == 400:
            print(f"🔥 Server Response: {response.text}")
        else:
            print(f"❌ Handshake Failed: {response.text}")
            return False

    except Exception as e:
        print(f"❌ Connection Error during handshake: {e}")
        return False

def get_session_token(settings):
    """
    ใช้ API Key แลก Session JWT (สำหรับใช้ทำงาน)
    """
    auth = settings.get("auth", {})
    api_key = auth.get("api_key")
    api_url = settings.get("api_url")

    if not api_key:
        return None

    try:
        response = requests.post(f"{api_url}/workers/auth", json={"api_key": api_key})
        
        if response.status_code == 200:
            token = response.json()["access_token"]
            print("🔄 Session Token Refreshed.")
            return token
        else:
            print(f"⚠️ Auth Failed: {response.status_code}")
            return None
    except Exception as e:
        print(f"❌ Connection Error during auth: {e}")
        return None

def perform_task(settings, iteration):
    """
    ฟังก์ชันทำงาน (วนลูป)
    """
    global current_jwt
    api_url = settings.get("api_url")

    # 1. ถ้าไม่มี JWT หรือ JWT หมดอายุ -> ไปขอใหม่
    if not current_jwt:
        current_jwt = get_session_token(settings)
        if not current_jwt:
            print("⏳ Waiting for network/auth...")
            return # ข้ามรอบนี้ไปก่อน

    # 2. ทำงานจริง (ยิง API)
    headers = {"Authorization": f"Bearer {current_jwt}"}
    
    try:
        # ตัวอย่างการส่งงาน
        response = requests.post(
            f"{api_url}/workers/submit-task", 
            json={"iteration": iteration, "status": "working"},
            headers=headers
        )

        # 3. กรณี Token หมดอายุ (401)
        if response.status_code == 401:
            print("⚠️ Token expired. Clearing session...")
            current_jwt = None # เคลียร์ทิ้ง รอบหน้าจะไปขอใหม่เองอัตโนมัติ
            
            # (Optional) ลองขอใหม่ทันทีเลยก็ได้ถ้าไม่อยากรอรอบหน้า
            # current_jwt = get_session_token(settings) 
            # if current_jwt: perform_task(settings, iteration)

        elif response.status_code == 200:
            print(f"✅ [Cycle {iteration}] Task Submitted.")
        else:
            print(f"⚠️ Server Error: {response.status_code}")

    except Exception as e:
        print(f"❌ Task Error: {e}")

def start_agent():
    print("🤖 Agent Starting...")
    
    # 1. โหลด Config
    settings = config.load_settings()
    auth = settings.get("auth", {})
    worker_id = auth.get("worker_id", "Unknown")
    
    print(f"🆔 Worker ID: {worker_id}")

    # 2. เช็คสถานะ (Credential Check)
    if auth.get("api_key"):
        print("🔑 Found API Key. Ready to work.")
        
    elif auth.get("registration_token"):
        print("🎫 Found Registration Token. Starting Handshake...")
        if not handshake(settings):
            print("💀 Handshake failed. Exiting.")
            time.sleep(100) 
            return # จบการทำงานถ้า Handshake ไม่ผ่าน
            
    else:
        print("⛔ No credentials found. Please re-download the agent.")
        print("   (Ensure .agent_key and secret.dat exist)")
        # รอสักพักเพื่อให้ User เห็น Error ก่อนปิด
        time.sleep(100) 
        return

    # 3. เข้าสู่ Main Loop
    interval = settings.get("task_interval_seconds", 60)
    iteration = 0
    
    while True:
        iteration += 1
        perform_task(settings, iteration)
        
        # Sleep
        time.sleep(interval)

if __name__ == "__main__":
    start_agent()