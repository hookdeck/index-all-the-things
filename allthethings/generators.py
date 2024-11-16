import httpx
from config import Config


class AsyncEmbeddingsGenerator:

    def generate(self, id, text):
        payload = {
            "version": "b6b7585c9640cd7a9572c6e129c9549d79c9c31f0d3fdce7baac7c67ca38f305",
            "input": {"text": text},
            "webhook": f"{Config.EMBEDDINGS_WEBHOOK_URL}/{id}",
            "webhook_events_filter": ["completed"],
        }

        response = httpx.request(
            "POST",
            f"{Config.HOOKDECK_REPLICATE_API_QUEUE_URL}/predictions",
            headers=Config.HOOKDECK_QUEUE_AUTH_HEADERS,
            json=payload,
        )

        return response.json()


class SyncEmbeddingsGenerator:

    def generate(self, text):
        payload = {
            "version": "b6b7585c9640cd7a9572c6e129c9549d79c9c31f0d3fdce7baac7c67ca38f305",
            "input": {"text": text},
        }

        response = httpx.request(
            "POST",
            "https://api.replicate.com/v1/predictions",
            headers={**Config.REPLICATE_API_AUTH_HEADERS, "Prefer": "wait"},
            json=payload,
            timeout=60,
        )

        return response.json()
