import time
from src.config import settings
from src.core.auth import AuthManager
from src.core.api_client import APIClient


def main():

    n = 0
    auth = AuthManager()
    client = APIClient(auth)

    print(f"🚀 Worker Started...")

    while True:
        n+=1
        payload = {
            "cnt": n,
            "status": "working"
        }

        result = client.post(settings.SUBMIT_TASK_ENDPOINT, payload)
        print(f"✅ [Cycle {n}] {result}")

        time.sleep(settings.poll_interval)

    

if __name__ == "__main__":
    main()