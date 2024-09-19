import http.client
import json

from config import Config
import re


# Define the headers for the Hookdeck API request
headers = {
    "Authorization": f"Bearer {Config.HOOKDECK_PROJECT_API_KEY}",
    "Content-Type": "application/json",
}


def create_connection(payload):
    conn = http.client.HTTPSConnection("api.hookdeck.com")
    conn.request(
        "PUT", "/latest/connections", body=json.dumps(payload), headers=headers
    )
    response = conn.getresponse()
    data = response.read().decode()
    conn.close()

    if response.status != 200:
        raise Exception(f"Failed to create connection: {data}")

    return json.loads(data)


# Create Replicate Audio Connection
replicate_audio = {
    "name": "replicate-audio",
    "source": {
        "name": "replicate-audio",
    },
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
    },
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
