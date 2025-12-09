import time
import sys
from datetime import datetime

# Import module config ที่เราเพิ่งสร้าง
import config 

def perform_task(settings, iteration):
    """
    ฟังก์ชันทำงานหลัก รับ settings เข้ามาเพื่อใช้ URL หรือ Token
    """
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    api_url = settings.get("api_url")
    auth_data = settings.get("auth")
    
    print(f"--- [Task Cycle {iteration}] ---")
    print(f"Time: {current_time}")
    
    if auth_data:
        token = auth_data.get("access_token")
        # print(f"Sending data to {api_url} using token {token[:10]}...")
        # requests.post(..., headers={"Authorization": f"Bearer {token}"})
    else:
        print("Warning: No Auth Token. Task running in offline mode.")
    
    print("----------------------------")

def start_agent():
    # 1. โหลดค่า Config ทั้งหมดมาเก็บไว้ในตัวแปรเดียว
    app_settings = config.load_settings()
    
    interval = app_settings.get("task_interval_seconds", 60)
    print(f"Agent starting... Interval: {interval}s")

    # ตรวจสอบว่าลงทะเบียนหรือยัง (มี Token ไหม?)
    if not app_settings.get("auth"):
        print("Agent is not registered. Please run handshake process first.")
        # ตรงนี้อาจจะเรียกฟังก์ชัน Handshake ถ้าต้องการ
        # sys.exit(1) 

    iteration = 0
    try:
        while True:
            iteration += 1
            
            # ส่ง settings เข้าไปใน task เผื่อมีการใช้ค่าข้างใน
            perform_task(app_settings, iteration)
            
            # Logic การรอเวลาให้ตรงวินาทีที่ 00
            now = datetime.now()
            sleep_time = interval - now.second % interval
            if sleep_time <= 0: sleep_time = interval
            
            time.sleep(sleep_time)

    except KeyboardInterrupt:
        print("\nAgent stopped.")

if __name__ == "__main__":
    start_agent()