import os
from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
HF_API_TOKEN = os.getenv("HF_API_TOKEN", "")

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")
VIEWER_DIR = os.path.join(os.path.dirname(__file__), "viewer")

os.makedirs(OUTPUT_DIR, exist_ok=True)
