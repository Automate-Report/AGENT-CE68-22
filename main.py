import time
from src.config.settings import settings
from src.core.auth import AuthManager
from src.core.api_client import APIClient
from src.test import test_xss

def main():


    n = 0
    auth = AuthManager()
    print(auth.verify_worker())
    client = APIClient(auth)

    print(f"🚀 Worker Started...")
    
    client.start_heartbeat_loop()

    

    # while True:
    n+=1
    payload = {
        "cnt": n,
        "status": "working"
    }

    result = client.post(settings.SUBMIT_TASK_ENDPOINT, payload)
    print(result)


    print(f"✅ [Cycle {n}] {result}")

    time.sleep(settings.poll_interval)
    result = test_xss()

    

if __name__ == "__main__":
    main()