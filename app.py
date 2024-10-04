import urllib
from urllib.parse import urlparse
from flask import Flask, jsonify, request, render_template, redirect, url_for, flash

from config import Config

from allthethings.mongo import Database
from allthethings.processors import get_asset_processor
from allthethings.generators import (
    get_embedding_generator,
    get_sync_embedding_generator,
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


@app.route("/search", methods=["GET"])
def search():
    return render_template("search.html", results=[])


@app.route("/search", methods=["POST"])
def search_post():
    query = request.form["query"]

    app.logger.info("Query submitted")
    app.logger.debug(query)

    results = query_vector_search(query)

    results = format_results(results)

    # TODO: look into warning logged here
    app.logger.debug("Formatted search results", results)

    return render_template("search.html", results=results, query=query)


@app.route("/process", methods=["POST"])
def process():
    url = request.form["url"]

    database = Database()
    collection = database.get_collection()

    exists = collection.find_one({"url": url})
    if exists is not None:
        flash("URL has already been indexed")
        return redirect(url_for("index"))

    # Only do a HEAD request to avoid downloading the whole file
    # This offloads the file downloading Replicate
    req = urllib.request.Request(url, method="HEAD")
    fetch = urllib.request.urlopen(req)

    if fetch.status != 200:
        flash("URL is not reachable")
        return redirect(url_for("index"))

    content_length = fetch.headers["Content-Length"]
    content_type = fetch.headers["Content-Type"]

    processor = get_asset_processor(content_type)

    if processor is None:
        flash('Unsupported content type "' + content_type + '"')
        return redirect(url_for("index"))

    collection.insert_one(
        {
            "url": url,
            "content_type": content_type,
            "content_length": content_length,
            "status": "SUBMITTED",
        }
    )

    prediction = processor.process(url)

    collection.update_one(
        filter={"url": url},
        update={
            "$set": {
                "status": "PROCESSING",
                "replicate_process_id": prediction.id,
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


def request_embeddings(id):
    app.logger.info("Requesting embeddings for %s", id)

    database = Database()
    collection = database.get_collection()

    asset = collection.find_one({"_id": id})

    if asset is None:
        raise RuntimeError("Asset not found")

    if asset["status"] != "PROCESSED":
        raise RuntimeError("Asset has not been processed")

    generator = get_embedding_generator()

    generate_request = generator.generate(asset["text"])

    collection.update_one(
        filter={"_id": id},
        update={
            "$set": {
                "status": "GENERATING_EMBEDDINGS",
                "replicate_embedding_id": generate_request.id,
            }
        },
    )


# Inspiration https://www.mongodb.com/developer/products/atlas/how-use-cohere-embeddings-rerank-modules-mongodb-atlas/#query-mongodb-vector-index-using--vectorsearch
def query_vector_search(q, prefilter={}, postfilter={}, path="embedding", topK=2):
    # Because the search is user-driven, we use the synchronous generator
    generator = get_sync_embedding_generator()

    generate_response = generator.generate(q)

    query_embedding = generate_response[0]["embedding"]

    app.logger.info("Query embedding generated")
    app.logger.debug(query_embedding)

    vs_query = {
        "index": "vector_index",
        "path": path,
        "queryVector": query_embedding,
        "numCandidates": 10,
        "limit": topK,
    }
    if len(prefilter) > 0:
        app.logger.info("Creating vector search query with pre filter")
        vs_query["filter"] = prefilter

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

    if len(postfilter.keys()) > 0:
        app.logger.info("Vector search query with post filter")
        postFilter = {"$match": postfilter}
        res = list(collection.aggregate([new_search_query, project, postFilter]))
    else:
        app.logger.info("Vector search query without post filter")
        res = list(collection.aggregate([new_search_query, project]))

    app.logger.info("Vector search query run")
    app.logger.debug(res)
    return res


@app.route("/webhooks/audio", methods=["POST"])
def webhook_audio():
    payload = request.json
    app.logger.info("Audio payload recieved")
    app.logger.debug(payload)

    database = Database()
    collection = database.get_collection()

    status = (
        "PROCESSING_ERROR" if "error" in payload and payload["error"] else "PROCESSED"
    )

    result = collection.find_one_and_update(
        filter={"replicate_process_id": payload["id"]},
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
        app.logger.error(
            "No document found for id %s to add audio transcript", payload["id"]
        )
        return jsonify({"error": "No document found to add audio transcript"}), 500

    app.logger.info("Transcription updated")
    app.logger.debug(result)

    request_embeddings(result["_id"])

    return "OK"


@app.route("/webhooks/embedding", methods=["POST"])
def webhook_embeddings():
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
        filter={"replicate_embedding_id": payload["id"]},
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
        return jsonify({"error": "No document found to update embedding"}), 500

    return "OK"
