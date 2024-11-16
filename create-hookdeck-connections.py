import httpx
import re
import hashlib
import os

from config import Config

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


# Outbound Replicate API Queue
replicate_api_queue_api_key = hashlib.sha256(os.urandom(32)).hexdigest()
replicate_api_queue = {
    "name": "replicate-api-queue",
    "source": {
        "name": "replicate-api-inbound",
        "verification": {
            "type": "API_KEY",
            "configs": {
                "header_key": Config.HOOKDECK_QUEUE_API_KEY_HEADER_NAME,
                "api_key": replicate_api_queue_api_key,
            },
        },
    },
    "rules": [
        {
            "type": "retry",
            "strategy": "exponential",
            "count": 5,
            "interval": 30000,
            "response_status_codes": ["429", "500"],
        }
    ],
    "destination": {
        "name": "replicate-api",
        "url": "https://api.replicate.com/v1/",
        "auth_method": {
            "type": "BEARER_TOKEN",
            "config": {
                "token": Config.REPLICATE_API_TOKEN,
            },
        },
    },
}

replicate_api_connection = create_connection(replicate_api_queue)

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
            "response_status_codes": ["!200", "!404"],
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
            "response_status_codes": ["!200", "!404"],
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

replicate_api_connection_url = replicate_api_connection["source"]["url"]
audio_webhook_url = replicate_audio_connection["source"]["url"]
embedding_webhook_url = replicate_embedding_connection["source"]["url"]

# Replace the .env URLs in the .env content
env_content = re.sub(
    r"HOOKDECK_REPLICATE_API_QUEUE_API_KEY=.*",
    f"HOOKDECK_REPLICATE_API_QUEUE_API_KEY={replicate_api_queue_api_key}",
    env_content,
)
env_content = re.sub(
    r"HOOKDECK_REPLICATE_API_QUEUE_URL=.*",
    f"HOOKDECK_REPLICATE_API_QUEUE_URL={replicate_api_connection_url}",
    env_content,
)
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
