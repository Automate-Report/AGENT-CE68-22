import redis
import json
import time

# ตั้งค่าให้ตรงกับที่ Backend/Worker ใช้
r = redis.Redis(host='10.60.1.214', port=5678, db=1)
queue_name = "system:queue:work:1" # เปลี่ยนเลข ID ให้ตรงกับ settings ของคุณ

def send_test_jobs():
    print(f"📡 Sending test jobs to {queue_name}...")
    
    test_jobs = [
        {"job_id": 101, "target_url": "http://161.246.6.1:8015/", "attack_type": "XSS", "credential": None},
        # {"job_id": 2, "target_url": "http://localhost:3000/", "attack_type": "xss", "credentials": None},
        # {"job_id": 3, "target_url": "https://ce-backend.onikla.org/", "attack_type": "XSS", "credentials": None},
        # {"job_id": 2, "target_url": "http://localhost:4040/#/", "attack_type": "sql_injection", "credential": None},
    ]

    for job in test_jobs:
        r.lpush(queue_name, json.dumps(job))
        print(f"✅ Pushed Job ID: {job['job_id']}")

if __name__ == "__main__":
    send_test_jobs()