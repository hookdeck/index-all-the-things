import httpx

from config import Config
import re


# Define the headers for the Hookdeck API request
headers = {
    "Authorization": f"Bearer {Config.HOOKDECK_PROJECT_API_KEY}",
    "Content-Type": "application/json",
}


def create_connection(payload):
    response = httpx.request(
        "PUT",
        "https://api.hookdeck.com/latest/connections",
        headers=headers,
        json=payload,
    )
    data = response.json()

    if response.status_code != 200:
        raise Exception(f"Failed to create connection: {data}")

    return data


# Create Replicate Audio Connection
replicate_audio = {
    "name": "replicate-audio",
    "source": {
        "name": "replicate-audio",
        # "verification": {
        #     "type": "REPLICATE",
        #     "configs": {
        #         "webhook_secret_key": Config.REPLICATE_WEBHOOKS_SECRET,
        #     },
        # },
    },
    "rules": [
        {
            "type": "retry",
            "strategy": "exponential",
            "count": 5,
            "interval": 30000,
            "response_status_codes": ["!404"],
        }
    ],
    "destination": {
        "name": "cli-replicate-audio",
        "cli_path": "/webhooks/audio",
    },
}

replicate_audio_connection = create_connection(replicate_audio)

# Create Replicate Embedding Connection
replicate_embedding = {
    "name": "replicate-embedding",
    "source": {
        "name": "replicate-embedding",
        # "verification": {
        #     "type": "REPLICATE",
        #     "configs": {
        #         "webhook_secret_key": Config.REPLICATE_WEBHOOKS_SECRET,
        #     },
        # },
    },
    "rules": [
        {
            "type": "retry",
            "strategy": "exponential",
            "count": 5,
            "interval": 30000,
            "response_status_codes": ["!404"],
        }
    ],
    "destination": {
        "name": "cli-replicate-embedding",
        "cli_path": "/webhooks/embedding",
    },
}

replicate_embedding_connection = create_connection(replicate_embedding)

# Update .env
with open(".env", "r") as file:
    env_content = file.read()

audio_webhook_url = replicate_audio_connection["source"]["url"]
embedding_webhook_url = replicate_embedding_connection["source"]["url"]

# Replace the webhooks URLs in the .env content
env_content = re.sub(
    r"AUDIO_WEBHOOK_URL=.*", f"AUDIO_WEBHOOK_URL={audio_webhook_url}", env_content
)
env_content = re.sub(
    r"EMBEDDINGS_WEBHOOK_URL=.*",
    f"EMBEDDINGS_WEBHOOK_URL={embedding_webhook_url}",
    env_content,
)

with open(".env", "w") as file:
    file.write(env_content)

print("Connections created successfully!")
