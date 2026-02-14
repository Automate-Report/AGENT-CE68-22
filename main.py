import os

# [FIX] บังคับให้ Playwright ไปหา Browser ในเครื่อง (System Path) 
# แทนที่จะหาในโฟลเดอร์ _internal ของ .exe
os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "0"


from src.core.worker_engine import WorkerEngine
from src.core.auth import AuthManager
from src.networking.bridge import BackendBridge
from src.test import run_security_test

def main():

    auth = AuthManager()

    client = BackendBridge(auth)
    client.start_heartbeat_loop()

    WorkerEngine().start()

    # run_security_test()


if __name__ == "__main__":
    main()