import time
from src.config import settings
from src.core.auth import AuthManager
from src.core.api_client import APIClient

# def task(n: int):
#     global current_jwt

#     if not current_jwt:
#         current_jwt=verify_worker()
#         if not current_jwt:
#             print("⏳ Waiting for network/verify...")
#             return
        
#     headers = {"Authorization" : f"Bearer {current_jwt}"}

#     try:
#         response = requests.post(
#             "http://localhost:8000/workers/submit-task",
#             json={"cnt": n, "status": "working"},
#             headers=headers
#         )

#         if response.status_code == 401:
#             print("⚠️ Token expired. Clearing session...")
#             current_jwt = None
#         elif response.status_code == 200:
#             print(f"✅ [Cycle {n}] Task Submitted.")
#         else:
#             print(f"⚠️ Server Error: {response.status_code}")
#     except Exception as e:
#         print(f"❌ Task Error: {e}")


def main():

    n = 0
    auth = AuthManager()
    client = APIClient(auth)

    print(f"🚀 Worker {settings.WORKER_ID} Started...")

    while True:
        n+=1
        payload = {
            "cnt": n,
            "status": "working"
        }

        client.post(settings.SUBMIT_TASK_ENDPOINT, payload)
        print(f"✅ [Cycle {n}] Task Submitted.")

        time.sleep(settings.POLL_INTERVAL)

    

if __name__ == "__main__":
    main()