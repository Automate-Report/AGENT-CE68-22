import redis
import json
import time

# ตั้งค่าให้ตรงกับที่ Backend/Worker ใช้
r = redis.Redis(host='127.0.0.1', port=5678, db=1)
queue_name = "queue:worker:1" # เปลี่ยนเลข ID ให้ตรงกับ settings ของคุณ

def send_test_jobs():
    print(f"📡 Sending test jobs to {queue_name}...")
    
    test_jobs = [
        {"id": 1, "target_url": "http://testphp.vulnweb.com/search.php", "attack_type": "xss", "credentials": None},
        # {"id": 102, "target_url": "http://xss-game.appspot.com", "attack_type": "xss", "credentials": {"user": "admin"}},
        # {"id": 103, "target_url": "http://demo.testfire.net", "attack_type": "sql_injection", "credentials": None},
        # {"id": 104, "target_url": "http://example.com", "attack_type": "xss", "credentials": None},
    ]

    for job in test_jobs:
        r.lpush(queue_name, json.dumps(job))
        print(f"✅ Pushed Job ID: {job['id']}")

if __name__ == "__main__":
    send_test_jobs()