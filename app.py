import os
from io import BytesIO
from urllib.parse import urlparse
from flask import Flask, jsonify, request, render_template, redirect, url_for, flash
import requests
import replicate
from dotenv import load_dotenv

from lib.mongo import get_mongo_client

load_dotenv()

app = Flask(
    __name__, static_url_path="", template_folder="templates", static_folder="static"
)
app.secret_key = os.getenv("SECRET_KEY")

AUDIO_WEBHOOK_URL = os.getenv("AUDIO_WEBHOOK_URL")


@app.route("/")
def index():
    client = get_mongo_client()
    if client is None:
        flash("Failed to connect to MongoDB")

    indexes = client["iaat"]["indexes"].find({})
    results = []
    for _idx, index in enumerate(indexes):
        parse_result = urlparse(index["url"])
        parsed_url = {
            "netloc": parse_result.netloc,
            "path": parse_result.path,
            "params": parse_result.params,
            "query": parse_result.query,
            "fragment": parse_result.fragment,
            "hostname": parse_result.hostname,
            "last_part": parse_result.path.rstrip("/").split("/")[-1],
        }
        index["parsed_url"] = parsed_url
        results.append(index)

    # print(results)

    return render_template("home.html", indexes=results)


@app.route("/process", methods=["POST"])
def process():
    url = request.form["url"]

    client = get_mongo_client()
    if client is None:
        flash("Failed to connect to MongoDB")
        return redirect(url_for("index"))

    exists = client["iaat"]["indexes"].find_one({"url": url})
    if exists is not None:
        flash("URL has already been indexed")
        return redirect(url_for("index"))

    response = requests.get(url)
    content_type = response.headers["Content-Type"]
    content = response.content
    # print(f"Content Type: {content_type}")

    if "audio/" not in content_type:
        flash('Unsupported content type "' + content_type + '"')
        return redirect(url_for("index"))

    client["iaat"]["indexes"].insert_one(
        {"url": url, "content_type": content_type, "status": "SUBMITTED"}
    )

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
    # print(">>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>")
    # print(prediction)
    # print(">>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>")

    client["iaat"]["indexes"].update_one(
        filter={"url": url},
        update={
            "$set": {
                "status": "PROCESSING",
                "replicate_id": prediction.id,
                "replicate_request": {
                    "model": prediction.model,
                    "version": prediction.version,
                    "status": prediction.status,
                    "input": prediction.input,
                    "logs": prediction.logs,
                    "created_at": prediction.created_at,
                    "urls": prediction.urls,
                },
            }
        },
    )

    flash(
        message="Processing: " + url + " with content type: " + content_type,
        category="success",
    )

    return redirect(url_for("index"))


@app.route("/webhooks/audio", methods=["POST"])
def audio_webhook():
    payload = request.json
    # print(payload)

    client = get_mongo_client()

    if client is None:
        return jsonify({"error": "Database connection failed"}), 500

    result = client["iaat"]["indexes"].update_one(
        filter={"replicate_id": payload["id"]},
        update={"$set": {"status": "PROCESSED", "replicate_response": payload}},
    )

    if result.modified_count == 0:
        return jsonify({"error": "No document found"}), 500

    return "OK"
