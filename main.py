import sys, os

# Get base path (works both frozen and normal)
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(__file__)

# Point to bundled browsers
os.environ["PLAYWRIGHT_BROWSERS_PATH"] = os.path.join(BASE_DIR, "ms-playwright")



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