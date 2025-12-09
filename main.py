import time 
from datetime import datetime

def perform_task(iteration):
    """
    ฟังก์ชันแกนหลักที่ทำงานทุกๆ 1 นาที
    """
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    print(f"--- [Task Cycle {iteration}] ---")
    print(f"Time Check: {current_time}")
    
    # จำลองการส่งข้อมูลที่ต้องใช้ Token ไปยัง Backend
    # headers = {"Authorization": f"Bearer {access_token}"}
    try:
        # สมมติว่ามี API สำหรับส่ง Status
        # requests.post(f"{API_URL}/agent/status", json={"time": current_time}, headers=headers)
        pass
    except Exception as e:
        print(f"Warning: Failed to send status to server. {e}")
    
    print("----------------------------")


# ----------------------------------------------------------------
# MAIN LOOP
# ----------------------------------------------------------------

def start_agent():
    # config = load_config()
    # access_token = config.get("access_token")

    # --- 1. Handshake (ถ้ายังไม่มี Token ถาวร) ---
    # if not access_token:
    #     reg_token = EMBEDDED_REG_TOKEN
        
    #     # ป้องกันกรณีรันไฟล์ Template เปล่าๆ
    #     if "REGISTRATION_TOKEN" in reg_token: 
    #         print("Error: Invalid installer. Please download from dashboard.")
    #         sys.exit(1)

    #     access_token = handshake_and_get_token(reg_token)
    #     if not access_token:
    #         print("Could not obtain Access Token. Exiting.")
    #         sys.exit(1)

    # print(f"Agent successfully authenticated. Starting main loop...")
    
    iteration = 0
    while True:
        iteration += 1
        try:
            perform_task(iteration)
            
        except Exception as e:
            print(f"!!! An unexpected error occurred: {e}. Retrying...")
            
        # --- PAUSE (Sleep) ---
        print(f"Sleeping for 60 seconds (Remaining: {60 - (datetime.now().second % 60)}s)...")
        time.sleep(60)

if __name__ == "__main__":
    start_agent()