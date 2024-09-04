import os
import urllib
from urllib.parse import urlparse
from flask import Flask, jsonify, request, render_template, redirect, url_for, flash
from dotenv import load_dotenv

from lib.mongo import get_mongo_client
from lib.processors import get_processor

load_dotenv()

app = Flask(
    __name__, static_url_path="", template_folder="templates", static_folder="static"
)
app.secret_key = os.getenv("SECRET_KEY")


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

    req = urllib.request.Request(url, method="HEAD")
    fetch = urllib.request.urlopen(req)

    if fetch.status != 200:
        flash("URL is not reachable")
        return redirect(url_for("index"))

    content_length = fetch.headers["Content-Length"]
    content_type = fetch.headers["Content-Type"]

    processor = get_processor(content_type)

    if processor is None:
        flash('Unsupported content type "' + content_type + '"')
        return redirect(url_for("index"))

    client["iaat"]["indexes"].insert_one(
        {
            "url": url,
            "content_type": content_type,
            "content_length": content_length,
            "status": "SUBMITTED",
        }
    )

    prediction = processor.process(url)

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


@app.route("/webhooks", methods=["POST"])
def webhook():
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
