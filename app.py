import os
from io import BytesIO
from flask import Flask, request, render_template, redirect, url_for, flash
import requests
import replicate
from dotenv import load_dotenv

load_dotenv()

app = Flask(
    __name__, static_url_path="", template_folder="templates", static_folder="static"
)
app.secret_key = os.getenv("SECRET_KEY")

AUDIO_WEBHOOK_URL = os.getenv("AUDIO_WEBHOOK_URL")


@app.route("/")
def index():
    return render_template("home.html")


@app.route("/process", methods=["POST"])
def process():
    url = request.form["url"]

    response = requests.get(url)
    content_type = response.headers["Content-Type"]
    content = response.content
    print(f"Content Type: {content_type}")

    buffer = BytesIO(content)

    model = replicate.models.get("openai/whisper")
    version = model.versions.get(
        "cdd97b257f93cb89dede1c7584e3f3dfc969571b357dbcee08e793740bedd854"
    )
    # model = "openai/whisper"
    # version = "cdd97b257f93cb89dede1c7584e3f3dfc969571b357dbcee08e793740bedd854"
    input = {
        "audio": buffer,
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

    # sync
    # output = replicate.run(
    #     model + ":" + version,
    #     input=input,
    # )

    prediction = replicate.predictions.create(
        version=version,
        input=input,
        webhook=AUDIO_WEBHOOK_URL,
        webhook_events_filter=["completed"],
    )
    print(prediction)

    flash("Received URL: " + url + " with content type: " + content_type)

    return redirect(url_for("index"))


@app.route("/webhooks/audio", methods=["POST"])
def audio_webhook():
    print(request.json)
    return "OK"
