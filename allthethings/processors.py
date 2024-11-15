import httpx
from config import Config


def get_asset_processor(
    content_type,
):
    if "audio/" in content_type:
        return AudioProcessor()
    elif "video/" in content_type:
        return None
    elif "image/" in content_type:
        return None
    else:
        return None


class AudioProcessor:
    def process(self, id, url):
        input = {
            "audio": url,
            "model": "large-v3",
            "language": "auto",
            "translate": False,
            "temperature": 0,
            "transcription": "plain text",
            "suppress_tokens": "-1",
            "logprob_threshold": -1,
            "no_speech_threshold": 0.6,
            "condition_on_previous_text": True,
            "compression_ratio_threshold": 2.4,
            "temperature_increment_on_fallback": 0.2,
        }

        payload = {
            "version": "cdd97b257f93cb89dede1c7584e3f3dfc969571b357dbcee08e793740bedd854",
            "input": input,
            "webhook": f"{Config.AUDIO_WEBHOOK_URL}/{id}",
            "webhook_events_filter": ["completed"],
        }

        response = httpx.request(
            "POST",
            f"{Config.HOOKDECK_REPLICATE_API_QUEUE_URL}/predictions",
            json=payload,
            headers=Config.REPLICATE_AUTH_HEADERS,
        )

        return response.json()
