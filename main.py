import sys, os

# เช็คจาก executable แทน sys.frozen
IS_EXE = not os.path.basename(sys.executable).startswith("python")

if IS_EXE:
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

if IS_EXE:
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = os.path.join(BASE_DIR, "ms-playwright")
    print(f"[DEBUG] PLAYWRIGHT_BROWSERS_PATH = {os.environ['PLAYWRIGHT_BROWSERS_PATH']}")

from src.core.worker_engine import WorkerEngine
from src.core.auth import AuthManager
from src.networking.bridge import BackendBridge

def main():

    auth = AuthManager()

    client = BackendBridge(auth)
    client.start_heartbeat_loop()

    WorkerEngine().start()



if __name__ == "__main__":
    main() 