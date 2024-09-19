import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    MONGODB_CONNECTION_URI = os.getenv("MONGODB_CONNECTION_URI")
    DB_NAME = "iaat"
    COLLECTION_NAME = "assets"
    SECRET_KEY = os.getenv("SECRET_KEY")
    AUDIO_WEBHOOK_URL = os.getenv("AUDIO_WEBHOOK_URL")
    EMBEDDINGS_WEBHOOK_URL = os.getenv("EMBEDDINGS_WEBHOOK_URL")
    HOOKDECK_PROJECT_API_KEY = os.getenv("HOOKDECK_PROJECT_API_KEY")
