import os
from dotenv import load_dotenv
import platform

load_dotenv()

class Config:
    BACKEND_URL = os.getenv("BACKEND_URL")
    WORKER_ID = int(os.getenv("WORKER_ID"))
    ACCESS_KEY = os.getenv("ACCESS_KEY")
    POLL_INTERVAL = int(os.getenv("POLL_INTERVAL"))
    HOSTNAME = platform.node()
    VERIFY_ENDPOINT = os.getenv("VERIFY_ENDPOINT")
    SUBMIT_TASK_ENDPOINT = os.getenv("SUBMIT_TASK_ENDPOINT")

settings = Config()