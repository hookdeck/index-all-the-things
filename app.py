import httpx
from urllib.parse import urlparse
from bson import ObjectId
import hmac
import hashlib
import base64
from flask import Flask, jsonify, request, render_template, redirect, url_for, flash

from config import Config

from allthethings.mongo import Database
from allthethings.processors import get_asset_processor

from allthethings.generators import (
    AsyncEmbeddingsGenerator,
    SyncEmbeddingsGenerator,
)

app = Flask(
    __name__, static_url_path="", template_folder="templates", static_folder="static"
)
app.secret_key = Config.SECRET_KEY


def format_results(results):
    formatted_results = []
    for _idx, index in enumerate(results):
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
        formatted_results.append(index)

    return formatted_results


@app.route("/")
def index():
    database = Database()

    indexes = database.get_collection().find({})
    results = format_results(indexes)

    app.logger.info("Homepage loading")
    app.logger.debug(results)

    return render_template("home.html", indexes=results)


@app.route("/process", methods=["POST"])
def process():
    url = request.form["url"]

    parsed_url = urlparse(url)
    if not all([parsed_url.scheme, parsed_url.netloc]):
        flash("Invalid URL")
        return redirect(url_for("index"))

    database = Database()
    collection = database.get_collection()

    exists = collection.find_one({"url": url})
    if exists is not None:
        flash("URL has already been indexed")
        return redirect(url_for("index"))

    # Only do a HEAD request to avoid downloading the whole file
    # This offloads the file downloading Replicate
    response = httpx.request("HEAD", url)

    if response.status_code != 200:
        flash("URL is not reachable")
        return redirect(url_for("index"))

    content_length = response.headers["Content-Length"]
    content_type = response.headers["Content-Type"]

    app.logger.debug(
        "Processing URL: %s, Content-Type: %s, Content-Length: %s",
        url,
        content_type,
        content_length,
    )

    processor = get_asset_processor(content_type)

    if processor is None:
        flash('Unsupported content type "' + content_type + '"')
        return redirect(url_for("index"))

    asset = collection.insert_one(
        {
            "url": url,
            "content_type": content_type,
            "content_length": content_length,
            "status": "SUBMITTED",
        }
    )

    try:
        response = processor.process(asset.inserted_id, url)
    except Exception as e:
        app.logger.error("Error processing asset: %s", e)
        collection.update_one(
            filter={"url": url},
            update={
                "$set": {
                    "status": "PROCESSING_ERROR",
                    "error": str(e),
                }
            },
        )
        flash("Error processing asset")
        return redirect(url_for("index"))

    collection.update_one(
        filter={"url": url},
        update={
            "$set": {
                "status": "PROCESSING",
                "processor_response": response,
            }
        },
    )

    flash(
        message="Processing: " + url + " with content type: " + content_type,
        category="success",
    )

    return redirect(url_for("index"))


@app.route("/search", methods=["GET"])
def search():
    query = request.args.get("query")
    if query is None:
        return render_template("search.html", results=[])

    app.logger.info("Query submitted")
    app.logger.debug(query)

    results = query_vector_search(query)

    if results is None:
        flash("Search embeddings generation failed")
        return redirect(url_for("search"))

    results = format_results(results)

    # TODO: look into warning logged here
    app.logger.debug("Formatted search results", results)

    return render_template("search.html", results=results, query=query)


def request_embeddings(id):
    app.logger.info("Requesting embeddings for %s", id)

    database = Database()
    collection = database.get_collection()

    asset = collection.find_one({"_id": ObjectId(id)})

    if asset is None:
        raise RuntimeError("Asset not found")

    if asset["status"] != "PROCESSED":
        raise RuntimeError("Asset has not been processed")

    generator = AsyncEmbeddingsGenerator()

    try:
        response = generator.generate(id, asset["text"])
    except Exception as e:
        app.logger.error("Error generating embeddings for %s: %s", id, e)
        raise

    collection.update_one(
        filter={"_id": ObjectId(id)},
        update={
            "$set": {
                "status": "GENERATING_EMBEDDINGS",
                "generator_response": response,
            }
        },
    )


# Inspiration https://www.mongodb.com/developer/products/atlas/how-use-cohere-embeddings-rerank-modules-mongodb-atlas/#query-mongodb-vector-index-using--vectorsearch
def query_vector_search(q):
    # Because the search is user-driven, we use the synchronous generator
    generator = SyncEmbeddingsGenerator()

    try:
        generator_response = generator.generate(q)
        app.logger.debug(generator_response)
    except Exception as e:
        app.logger.error("Error generating embeddings: %s", e)
        return None

    if generator_response["output"] is None:
        app.logger.debug("Embeddings generation timed out")
        return None

    query_embedding = generator_response["output"][0]["embedding"]

    app.logger.info("Query embedding generated")
    app.logger.debug(query_embedding)

    vs_query = {
        "index": "vector_index",
        "path": "embedding",
        "queryVector": query_embedding,
        "numCandidates": 100,
        "limit": 10,
    }

    new_search_query = {"$vectorSearch": vs_query}

    app.logger.info("Vector search query created")
    app.logger.debug(new_search_query)

    project = {
        "$project": {
            "score": {"$meta": "vectorSearchScore"},
            "_id": 0,
            "url": 1,
            "content_type": 1,
            "content_length": 1,
            "text": 1,
        }
    }

    database = Database()
    collection = database.get_collection()

    res = list(collection.aggregate([new_search_query, project]))

    app.logger.info("Vector search query run")
    app.logger.debug(res)
    return res


def verify_webhook(request):
    if Config.HOOKDECK_WEBHOOK_SECRET is None:
        app.logger.error("No HOOKDECK_WEBHOOK_SECRET found.")
        return False

    hmac_header = request.headers.get("x-hookdeck-signature")

    hash = base64.b64encode(
        hmac.new(
            Config.HOOKDECK_WEBHOOK_SECRET.encode(), request.data, hashlib.sha256
        ).digest()
    ).decode()

    verified = hash == hmac_header
    app.logger.debug("Webhook signature verification: %s", verified)
    return verified


@app.route("/webhooks/audio/<id>", methods=["POST"])
def webhook_audio(id):
    if not verify_webhook(request):
        app.logger.error("Webhook signature verification failed")
        return jsonify({"error": "Webhook signature verification failed"}), 401

    payload = request.json
    app.logger.info("Audio payload received for id %s", id)
    app.logger.debug(payload)

    database = Database()
    collection = database.get_collection()

    status = (
        "PROCESSING_ERROR" if "error" in payload and payload["error"] else "PROCESSED"
    )

    result = collection.find_one_and_update(
        filter={"_id": ObjectId(id)},
        update={
            "$set": {
                "status": status,
                "text": payload["output"]["transcription"],
                "replicate_response": payload,
            }
        },
        return_document=True,
    )

    if result is None:
        app.logger.error("No document found for id %s to add audio transcript", id)
        return jsonify({"error": "No document found to add audio transcript"}), 404

    app.logger.info("Transcription updated")
    app.logger.debug(result)

    request_embeddings(id)

    return "OK"


@app.route("/webhooks/embedding/<id>", methods=["POST"])
def webhook_embeddings(id):
    if not verify_webhook(request):
        app.logger.error("Webhook signature verification failed")
        return jsonify({"error": "Webhook signature verification failed"}), 401

    payload = request.json
    app.logger.info("Embeddings payload recieved")
    app.logger.debug(payload)

    status = (
        "EMBEDDINGS_ERROR" if "error" in payload and payload["error"] else "SEARCHABLE"
    )

    embedding = payload["output"][0]["embedding"]

    database = Database()
    collection = database.get_collection()

    result = collection.update_one(
        filter={"_id": ObjectId(id)},
        update={
            "$set": {
                "status": status,
                "embedding": embedding,
                "replicate_embeddings_response": payload,
            }
        },
    )

    if result.matched_count == 0:
        app.logger.error(
            "No document found for id %s to update embedding", payload["id"]
        )
        return jsonify({"error": "No document found to update embedding"}), 404

    return "OK"
