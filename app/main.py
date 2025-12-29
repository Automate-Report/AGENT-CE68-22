import requests
import platform

current_jwt = None

def verify_worker():
    response = requests.post("http://localhost:8000/workers/verify", json={
        "key": "nHRws3kAxXUj0GgoOb3ecZZoIPPTEvxgGDhZ9UjxDFk",
        "worker_id": 7,
        "hostname": platform.node()
    })

    if response.status_code == 200:
        print("✅ Success: Verified")
        print(response.json())
        data = response.json()
        current_jwt = data.get("token")
        return current_jwt
    else:
        # response.text will contain the "detail" message from the exception
        print(f"❌ Handshake Failed: {response.status_code} - {response.text}")
        return None

def task(n: int):
    global current_jwt

    if not current_jwt:
        current_jwt=verify_worker()
        if not current_jwt:
            print("⏳ Waiting for network/verify...")
            return
        
    headers = {"Authorization" : f"Bearer {current_jwt}"}

    try:
        response = requests.post(
            "http://localhost:8000/workers/submit-task",
            json={"cnt": n, "status": "working"},
            headers=headers
        )

        if response.status_code == 401:
            print("⚠️ Token expired. Clearing session...")
            current_jwt = None
        elif response.status_code == 200:
            print(f"✅ [Cycle {n}] Task Submitted.")
        else:
            print(f"⚠️ Server Error: {response.status_code}")
    except Exception as e:
        print(f"❌ Task Error: {e}")


def main():
    print("Hello")
    n = 0
    while True:
        task(n)
        n+=1

    

if __name__ == "__main__":
    main()