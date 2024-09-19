import replicate

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
    def __init__(self):
        self.WEBHOOK_URL = Config.AUDIO_WEBHOOK_URL
        self.model = replicate.models.get("openai/whisper")
        self.version = self.model.versions.get(
            "cdd97b257f93cb89dede1c7584e3f3dfc969571b357dbcee08e793740bedd854"
        )

    def process(self, url):
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

        prediction = replicate.predictions.create(
            version=self.version,
            input=input,
            webhook=self.WEBHOOK_URL,
            webhook_events_filter=["completed"],
        )

        return prediction
