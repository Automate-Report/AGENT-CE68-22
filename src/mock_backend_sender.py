import redis
import json
import time

# ตั้งค่าให้ตรงกับที่ Backend/Worker ใช้
r = redis.Redis(host='127.0.0.1', port=5678, db=1)
queue_name = "system:queue:work:2" # เปลี่ยนเลข ID ให้ตรงกับ settings ของคุณ

def send_test_jobs():
    print(f"📡 Sending test jobs to {queue_name}...")
    
    test_jobs = [
        {"job_id": 1, "target_url": "http://localhost:4040/#/", "attack_type": "sql_injection", "credential": None},
        # {"job_id": 2, "target_url": "http://localhost:3000/", "attack_type": "xss", "credentials": None},
        # {"job_id": 3, "target_url": "http://localhost:4050/login.php", "attack_type": "sql_injection", "credentials": None},
        # {"job_id": 2, "target_url": "http://localhost:4040/#/", "attack_type": "sql_injection", "credential": None},
    ]

    for job in test_jobs:
        r.lpush(queue_name, json.dumps(job))
        print(f"✅ Pushed Job ID: {job['job_id']}")

if __name__ == "__main__":
    send_test_jobs()