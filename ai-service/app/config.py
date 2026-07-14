import os
from dotenv import load_dotenv

# Path to the .env file at the project root (two levels up from ai-service/app)
base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
env_path = os.path.join(base_dir, '.env')

if os.path.exists(env_path):
    load_dotenv(env_path)
else:
    load_dotenv()

DB_HOST = os.getenv("DB_HOST", "192.168.40.140")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "stajor")
DB_USER = os.getenv("DB_USER", "stajor1")
DB_PASSWORD = os.getenv("DB_PASSWORD", "stajor1*-")

DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
