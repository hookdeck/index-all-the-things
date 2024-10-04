import replicate

from config import Config


class AsyncEmbeddingsGenerator:
    def __init__(self):
        self.WEBHOOK_URL = Config.EMBEDDINGS_WEBHOOK_URL
        self.model = replicate.models.get("replicate/all-mpnet-base-v2")
        self.version = self.model.versions.get(
            "b6b7585c9640cd7a9572c6e129c9549d79c9c31f0d3fdce7baac7c67ca38f305"
        )

    def generate(self, text):
        input = {"text": text}

        prediction = replicate.predictions.create(
            version=self.version,
            input=input,
            webhook=self.WEBHOOK_URL,
            webhook_events_filter=["completed"],
        )

        return prediction


class SyncEmbeddingsGenerator:

    def generate(self, text):

        input = {"text": text}
        output = replicate.run(
            "replicate/all-mpnet-base-v2:b6b7585c9640cd7a9572c6e129c9549d79c9c31f0d3fdce7baac7c67ca38f305",
            input=input,
        )

        return output
