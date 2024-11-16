# H1. Index All the Things: Using Replicate, MongoDB, and Hookdeck to Build Scalable Content Type Agnostic Vector Search with Python and Flask

## H2. Introduction

In this tutorial, we'll build a Flask application that allows a user to index and then search anything on the Internet that has a publically accessible URL. That's right! Ask the app to index an MP3 or WAV file, an HTML or Text file, or a MOV or MP4 file, and it will use the power of Replicate AI to create textual representation of that file and the results will be stored in MongoDB Atlas. As long as there's an LLM that can analyze the resource and create a textual representation, it can be indexed. Then, all those indexed files, no matter the originating file type, can be searched using text using MongoDB Atlas. We'll use the Hookdeck event gateway as a serverless queue, managing API requests and asynchronous webhook callbacks between Replicate and our Flask app to ensure our architecture is structured to scale with demand.

We'll begin by getting setting up the required services and getting the Flask application up and running. Then, we'll follow the journey of data through key components and code within the app, covering the indexing request is submitted, the content-type analyzed, a textual representation is generated, a vector embedding is generated and stored, and the content is ultimately made available for search within a vector search index.

## H2. Architecture Overview

Scalability is often overhyped, but it remains an important aspect of building robust applications. One of the benefits of using serverless and cloud-hosted providers is the ability to offload work to specialized services. Also important to any scalable architecture is a way of ensuring services aren't overloaded, and your application is fault-tolerant. In this tutorial, we leverage several such services to handle different aspects of our application.

First let's take a look at the services:

- **[Replicate](https://replicate.com)**: Provides open-source machine learning models, accessible via an API.
- **[MongoDB Atlas](https://www.mongodb.com/products/platform/atlas-database)**: An integrated suite of data services centered around a cloud database designed to accelerate and simplify how you build with data. 
- **[Hookdeck](https://hookdeck.com?ref=mongodb-iatt**: An event gateway that provides engineering teams with infrastructure and tooling to build and manage event-driven applications.

Next, let's see how they're used.

TODO: image

- **Replicate**: Replicate handles AI inference, producing text and embeddings and allowing us to offload the computationally intensive tasks of running machine learning models. We use different LLMs for analyzing different content types.
- **MongoDB Atlas**: MongoDB Atlas provides database storage and vector search capabilities, ensuring our data is stored efficiently and can be queried quickly.
- **Hookdeck**: Hookdeck acts as a serverless queue for a) ensuring Replicate API requests do not exceed rate limits and can be retried, and b) ingesting, delivery and retrying webhooks from Replicate to ensure reliable ingestion of events. Note: We'll also use the [Hookdeck CLI](https://hookdeck.com/docs/cli?ref=mongodb-iatt) to receive webhooks in our local development environment.

By utilizing these cloud-based services, we can focus on building the core functionality of our application while ensuring it remains scalable and efficient. Webhooks, in particular, allow for scalability by enabling [asynchronous AI workflows](https://hookdeck.com/blog/asynchronous-ai?ref=mongodb-iatt), offloading those high compute usage scenarios to the third-party services, and just receiving callbacks via a webhook when work is completed.

## H2. Prerequisites

Before you begin, ensure you have the following:

- A free [Hookdeck account](https://dashboard.hookdeck.com/signup?ref=mongodb-iatt)
- The [Hookdeck CLI installed](https://hookdeck.com/docs/cli?ref=mongodb-iatt)
- A free [MongoDB Atlas account](https://www.mongodb.com/cloud/atlas/register)
- A free [Replicate account](https://replicate.com/signin)
- [Python 3](https://www.python.org/downloads/)
- [Poetry](https://python-poetry.org/docs/#installation) for package management

## H2: Get the App Up and Running

Let's begin by getting the application up and running and seeing it in action.

### H3: Get the Code

Begin by getting the application codebase.

```sh
git clone https://github.com/hookdeck/index-all-the-things.git
```

Active a virtual environment with Poetry:

```sh
poetry shell
```

And install the app dependencies:

```sh
poetry install
```

### H3: Configure the App

The application needs credentials for the services it interacts with.

Copy the example `.env-example` file to a new `.env` file:

```sh
cp .env-example .env
```

Update the values within `.env` as follows:

- `SECRET_KEY`: See the [`SECRET_KEY` Flask docs](https://flask.palletsprojects.com/en/stable/config/#SECRET_KEY).
- `MONGODB_CONNECTION_URI`: Populate with a MongoDB Atlas connection string with a **Read and write to any database** role. See the [Get Connection String docs](https://www.mongodb.com/docs/guides/atlas/connection-string/).
- `HOOKDECK_PROJECT_API_KEY`: Get an API Key from the **Project** -> **Settings** -> **Secrets** section of the [Hookdeck Dashboard](https://dashboard.hookdeck.com?ref=mongodb-iatt).
- `REPLICATE_API_TOKEN`: [Create an API token](https://replicate.com/account/api-tokens) in the Replicate dashboard.
- `REPLICATE_WEBHOOKS_SECRET`: Go to the [Webhooks section](https://replicate.com/account/webhook) of the Replicate dashboard and click the **Show signing key** button.
- `HOOKDECK_REPLICATE_API_QUEUE_API_KEY`, `HOOKDECK_REPLICATE_API_QUEUE_URL`, `AUDIO_WEBHOOK_URL` and `EMBEDDINGS_WEBHOOK_URL` will be automatically populated in the next step.

### H3: Create Hookdeck Connections

[Hookdeck Connections](https://hookdeck.com/docs/connections?ref=mongodb-iatt) are used to route inbound HTTP request received by a [Hookdeck Source](https://hookdeck.com/docs/sources?ref=mongodb-iatt) to a [Hookdeck Destination](https://hookdeck.com/docs/destinations?ref=mongodb-iatt).

The `create-hookdeck-connections.py` script automatically creates the following Hookdeck Connections that:

1. Route requests made to Hookdeck URLs through to the locally running application via the Hookdeck CLI. Here, Hookdeck is used as an inbound queue.
2. Route request made to a Hookdeck URL through to the Replicate API. Hookdeck is used as an outbound queue in this situation.

The script also updates the `.env` file with the Source URLs that handle the webhooks. Let's go through the details of the script.

First, ensure you have the necessary imports and define the authentication and content-type headers for the Hookdeck API request:

```py
import httpx
import re
import hashlib
import os

from config import Config

headers = {
    "Authorization": f"Bearer {Config.HOOKDECK_PROJECT_API_KEY}",
    "Content-Type": "application/json",
}
```

Next, define a function to create a Connection to the Hookdeck API:

```py
def create_connection(payload):
    response = httpx.request(
        "PUT",
        "https://api.hookdeck.com/latest/connections",
        headers=headers,
        json=payload,
    )
    data = response.json()

    if response.status_code != 200:
        raise Exception(f"Failed to create connection: {data}")

    return data
```

This function makes `PUT` request to the Hookdeck API with the [upsert Connection payload](https://hookdeck.com/docs/api#createupdate-a-connection?ref=mongodb-iatt), and handles the response. If the response status is not `200` (OK), an exception is raised. The function returns the parsed JSON response.

The first connection to be created is one for the Replicate API outbound queue:

```py
replicate_api_queue_api_key = hashlib.sha256(os.urandom(32)).hexdigest()
replicate_api_queue = {
    "name": "replicate-api-queue",
    "source": {
        "name": "replicate-api-inbound",
        "verification": {
            "type": "API_KEY",
            "configs": {
                "header_key": Config.HOOKDECK_QUEUE_API_KEY_HEADER_NAME,
                "api_key": replicate_api_queue_api_key,
            },
        },
    },
    "rules": [
        {
            "type": "retry",
            "strategy": "exponential",
            "count": 5,
            "interval": 30000,
            "response_status_codes": ["429", "500"],
        }
    ],
    "destination": {
        "name": "replicate-api",
        "url": "https://api.replicate.com/v1/",
        "auth_method": {
            "type": "BEARER_TOKEN",
            "config": {
                "token": Config.REPLICATE_API_TOKEN,
            },
        },
    },
}

replicate_api_connection = create_connection(replicate_api_queue)
```

The Connection has a `name`, a `source`, and a `destination`. The `source` also has a `name` and a `verification`. The `verification` instructs Hookdeck how to authenticate requests. Since the connection is acting as an API queue, we're using the `API_KEY` type with the `header_key` set to the value defined in `Config.HOOKDECK_QUEUE_API_KEY_HEADER_NAME` and the `api_key` value set to the generated hash stored in `replicate_api_queue_api_key`.

The `rules` define a request retry strategy to use when interacting with the Replicate API. In this case, we're stating to retry up to 5 time, using an interval of `30000` milliseconds, but apply an `exponential` back off retry strategy. Also, we're using the `response_status_codes` option to inform Hookdeck to only retry on `429` and `500` HTTP responses. See the [Hookdeck Retry docs](https://hookdeck.com/docs/retries?ref=mongodb-iatt) for more information on retries and the [Hookdeck Rules](https://hookdeck.com/docs/connections?ref=mongodb-iatt#connection-rules) docs for information on other types of rules that are available.

The `url` on the Destination is the base URL for the Replicate API. Hookdeck uses path forwarding by default so any path appended to the Hookdeck Source URL will also be appending to the destination URL. For example, a request to a Hookdeck Source with URL `https://hkdk.events/{id}/predictions` will result in a request to a connected Destination of `https://api.replicate.com/v1/predictions` where the Destination has a base URL of `https://api.replicate.com/v1/`. Hookdeck acts very much like a proxy in this scenario.

The `auth_method` on the Destination is of type `BEARER_TOKEN` with a `config.token` set to the value of the `REPLICATE_API_TOKEN` environment variable. This allows Hookdeck to make authenticated API calls to Replicate.

Now, create a Connection for the Replicate Audio webhooks to handle audio analysis callbacks:

```py
replicate_audio = {
    "name": "replicate-audio",
    "source": {
        "name": "replicate-audio",
        "verification": {
            "type": "REPLICATE",
            "configs": {
                "webhook_secret_key": Config.REPLICATE_WEBHOOKS_SECRET,
            },
        },
    },
    "rules": [
        {
            "type": "retry",
            "count": 5,
            "interval": 30000,
            "strategy": "exponential",
            "response_status_codes": ["!404"],
        }
    ],
    "destination": {
        "name": "cli-replicate-audio",
        "cli_path": "/webhooks/audio",
    },
}

replicate_audio_connection = create_connection(replicate_audio)
```

The Replicate Audio webhook callback connection uses a `verification` of type `REPLICATE` with a `configs.webhook_secret_key` value set from the `REPLICATE_WEBHOOKS_SECRET` value we stored in the `.env` file. This enables and instructs Hookdeck to verify that the webhook has come from Replicate.

The `rules` for this inbound Connection are similar to the outbound connection and define a delivery retry strategy to follow if any requests to our application's webhook endpoint fail. The only difference is the `response_status_codes` informs Hookdeck not retry if it receives a `200` or `404` response.

The `destination` has a `name` and a `cli_path` that informs Hookdeck that the Destination is the Hookdeck CLI and the path that the request should be forwarded to is `/webhooks/audio`.

Next, create a connection for Replicate Embeddings webhook callbacks:

```py
replicate_embedding = {
    "name": "replicate-embedding",
    "source": {
        "name": "replicate-embedding",
        "verification": {
            "type": "REPLICATE",
            "configs": {
                "webhook_secret_key": Config.REPLICATE_WEBHOOKS_SECRET,
            },
        },
    },
    "rules": [
        {
            "type": "retry",
            "count": 5,
            "interval": 30000,
            "strategy": "exponential",
            "response_status_codes": ["!200", "!404"],
        }
    ],
    "destination": {
        "name": "cli-replicate-embedding",
        "cli_path": "/webhooks/embedding",
    },
}

replicate_embedding_connection = create_connection(replicate_embedding)
```

Finally, update the `.env` file with some of the generated values:

```py
# Update .env
with open(".env", "r") as file:
    env_content = file.read()

replicate_api_connection_url = replicate_api_connection["source"]["url"]
audio_webhook_url = replicate_audio_connection["source"]["url"]
embedding_webhook_url = replicate_embedding_connection["source"]["url"]

# Replace the .env URLs in the .env content
env_content = re.sub(
    r"HOOKDECK_REPLICATE_API_QUEUE_API_KEY=.*",
    f"HOOKDECK_REPLICATE_API_QUEUE_API_KEY={replicate_api_queue_api_key}",
    env_content,
)
env_content = re.sub(
    r"HOOKDECK_REPLICATE_API_QUEUE_URL=.*",
    f"HOOKDECK_REPLICATE_API_QUEUE_URL={replicate_api_connection_url}",
    env_content,
)
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

print("Connections created successfully!")
```

This code reads the current `.env` content, replaces the lines with existing environmental variable placeholders using regular expressions, and writes the updated content back to the `.env` file. This ensures that the environment variables such as the webhook URLs are up-to-date.

Run the script:

```sh
poetry run python create-hookdeck-connections.py
```

Check your `.env` file to ensure all values are populated.

Also, navigate to the **Connections** section of the Hookdeck dashboard and check the visual representation of your connection.

![Hookdeck Connection in the Hookdeck Dashboard](<hookdeck-connections.png>)

### H3: Create MongoDB Atlas Indexes

In order to efficiently search a MongoDB database you need indexes. For MongoDB vector search you must create an [Atlas Vector Search Index](https://www.mongodb.com/docs/atlas/atlas-vector-search/vector-search-overview/#atlas-vector-search-indexes). The `create-indexes.py` script automates the creation and updating of the search indexes in MongoDB using the `pymongo` library.

First, ensure you have the necessary imports and initialize the database connection:

```py
from allthethings.mongo import Database
from pymongo.operations import SearchIndexModel

database = Database()
collection = database.get_collection()
```

`Database` is defined in `allthethings/mongo.py` and provides utility access to the `assets` collection in the `iaat` database, with these string values defined in `config.py`.

Next, ensure that the required collection exists within the database so that the indexes can be created:

```py
if collection.name not in collection.database.list_collection_names():
    print("Creating empty collection so indexes can be created.")
    collection.database.create_collection(collection.name)
```

With the collection created, define a function to create or update search indexes:

```py
def create_or_update_search_index(index_name, index_definition, index_type):
    indexes = list(collection.list_search_indexes(index_name))

    if len(indexes) == 0:
        print(f'Creating search index: "{index_name}"')
        index_model = SearchIndexModel(
            definition=index_definition,
            name=index_name,
            type=index_type,
        )
        collection.create_search_index(model=index_model)

    else:
        print(f'Search index "{index_name}" already exists. Updating.')
        collection.update_search_index(name=index_name, definition=index_definition)
```

This function checks if an index with the given `index_name` already exists. If it does not exist, it creates a new search index using the provided definition and type. If it exists, it updates the existing index with the new definition.

Now, create a vector search index for embeddings:

```py
vector_result = create_or_update_search_index(
    "vector_index",
    {
        "fields": [
            {
                "type": "vector",
                "path": "embedding",
                "numDimensions": 768,
                "similarity": "euclidean",
            }
        ]
    },
    "vectorSearch",
)
```

This creates or updates a vector search index named "vector_index" for the `embedding` field.

Finally, create a search index for the `url` field as this is used to determine if a URL has already been indexed:

```py
create_or_update_search_index(
    "url_index",
    {
        "mappings": {
            "fields": {
                "url": {
                    "type": "string",
                },
            },
        }
    },
    "search",
)

print("Indexes created successfully!")
```

Run the script:

```sh
poetry run python create-indexes.py
```

Go to the **Atlas Search** section within the MongoDB Atlas dashboard and check the search indexes have been created.

![MongoDB Atlas Dashboard Atlas Search indexes](<mongodb-atlas-search-indexes.png>)

### H3: Check the App is Working

In one terminal window, run the Flask application:

```sh
poetry run python -m flask --app app --debug run
```

In a second terminal window, create a localtunnel using the Hookdeck CLI:

```sh
hookdeck listen 5000 '*'
```

This command listens to all Hookdeck Sources connected to a CLI Destination, routing webhooks to the application running locally on port 5000.

When you run the command you will see output similar to the following:

```sh
Listening for events on Sources that have Connections with CLI Destinations

Dashboard
👉 Inspect and replay events: https://dashboard.hookdeck.com?team_id=tm_{id}

Sources
🔌 replicate-embedding URL: https://hkdk.events/{id}
🔌 replicate-audio URL: https://hkdk.events/{id}

Connections
replicate-embedding -> replicate-embedding forwarding to /webhooks/embedding
replicate-audio -> replicate-audio forwarding to /webhooks/audio

> Ready! (^C to quit)
```

Open `localhost:5000` in your web browser to ensure the Flask app is running.

![Index All the The Things App](<iaat-first-run.png>)

## H2: Submit Content for Analysis and Indexing

With the app running, it's time to submit an asset for indexing.

Click **Bruce (mp3)** under the **Examples** header to populate the in-app search bar with a URL and click **Submit**.

![Index All the The Things App](<iaat-bruce-submitted.png>)

Submitting the form, sends the URL to a `/process` endpoint as a `POST` request. Let's walk through what that code does.

First, define the `/process` route in `app.py`:

```py
@app.route("/process", methods=["POST"])
def process():
    url = request.form["url"]

    parsed_url = urlparse(url)
    if not all([parsed_url.scheme, parsed_url.netloc]):
        flash("Invalid URL")
        return redirect(url_for("index"))
```

This route handles the `POST` request to the `/process` endpoint and retrieves the URL from the form data submitted by the user. It validates the URL and redirects to the index page with an error message if it's not.

Next, check if the URL already exists in the database:

```py
    database = Database()
    collection = database.get_collection()

    exists = collection.find_one({"url": url})

    if exists is not None:
        flash("URL has already been indexed")
        return redirect(url_for("index"))
```

If the URL is already indexed, flash a message to the user and redirect them to the index page.

Perform a `HEAD` request to validate the URL and retrieve its headers:

```py
    req = urllib.request.Request(url, method="HEAD")
    fetch = urllib.request.urlopen(req)

    if fetch.status != 200:
        flash("URL is not reachable")
        return redirect(url_for("index"))
```

This code sends a `HEAD` request to the URL to avoid downloading the entire file. If the URL is not reachable (status code is not 200), flash a message to the user and redirect them to the index page.

Retrieve the content type and length from the response headers:

```py
    content_length = fetch.headers["Content-Length"]
    content_type = fetch.headers["Content-Type"]
```

This code extracts the content length and content type from the response headers.

Retrieve the appropriate asset processor based on the content type:

```py
    processor = get_asset_processor(content_type)

    if processor is None:
        flash('Unsupported content type "' + content_type + '"')
        return redirect(url_for("index"))
```

If no processor is found for the content type, flash a message to the user and redirect them to the index page.

The `get_asset_processor` function, defined in `allthethings/processors.py`, returns a processor used to analyze the contents of an asset based on the `content_type`.

```py
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
```

In this case, the file is an MP3 the `content_type` is `audio/mpeg`, so return an `AudioProcessor` instance.

Insert the URL, along with its content type and length, into the database with a status of `SUBMITTED`:

```py
    asset = collection.insert_one(
        {
            "url": url,
            "content_type": content_type,
            "content_length": content_length,
            "status": "SUBMITTED",
        }
    )
```

Process the URL using the asset processor, an `AudioProcessor`, and obtain the prediction results:

```py
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
```

Let's look at the `AudioProcessor` from `allthethings/processors.py` in more detail to understand what this does:

```py
import httpx
from config import Config

...

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
            headers=Config.HOOKDECK_QUEUE_AUTH_HEADERS,
            json=payload,
        )

        return response.json()
```

`process` method processes the audio URL by creating a prediction request passing the `payload` as the JSON body.

`payload` includes `webhooks` which consists of the `Config.AUDIO_WEBHOOK_URL` with an appended path (`/{id}`) that indicates which asset the callback is for. The use of the `webhook_events_filter=["completed"]` filter informs Replicate to only send a webhook when the prediction is completed.

The `payload.version` instructs Replicate to use the [OpenAI Whisper model](https://replicate.com/openai/whisper) for audio to text. The `input` includes details such as the language should be auto-detected and the transcription should be in `plain text`. 

Since we're using Hookdeck as an outbound API queue, the request uses the `Config.HOOKDECK_REPLICATE_API_QUEUE_URL` with the API path `/predications` suffix. The appropriate auth headers are also used from `Config.HOOKDECK_QUEUE_AUTH_HEADERS`.

Back in `app.py`, update the database with the processing status and pending prediction details:

```py
    collection.update_one(
        filter={"url": url},
        update={
            "$set": {
                "status": "PROCESSING",
                "processor_response": response,
            }
        },
    )
```

The `processor_response` value is stored for debug purposes as it contains a Hookdeck request ID that can be useful.

Flash a success message to the user and redirect them to the index page:

```py
    flash(
        message="Processing: " + url + " with content type: " + content_type,
        category="success",
    )

    return redirect(url_for("index"))
```

At this point, the Flask application has offloaded all the work to Replicate and, from a data journey perspective, we're waiting for the predication completed webhook.

<!-- Up to here with 1st draft review -->

### H3: Handle Prediction Completion Webhook

Once Replicate completes the predication, it makes a webhook callback to Hookdeck. Hookdeck instantly verifies the event came from Replicate, ingests the webhook, pushing the data onto a queue for processing and delivery. Based on the current Hookdeck Connection setup, the webhook event is delivered to the CLI and then to the `/webhooks/audio` endpoint of the Flask application. Let's look at the code that handles the `/webhooks/audio` request.

First, define the `/webhooks/audio` route in `app.py`:

```py
@app.route("/webhooks/audio", methods=["POST"])
def webhook_audio():
    payload = request.json
    app.logger.info("Audio payload received")
    app.logger.debug(payload)
```

This route handles `POST` requests to the `/webhooks/audio` endpoint. It retrieves the JSON payload from the webhook callback from Replicate.

Next, determine the processing status based on the presence of an error in the payload:

```py
    database = Database()
    collection = database.get_collection()

    status = (
        "PROCESSING_ERROR" if "error" in payload and payload["error"] else "PROCESSED"
    )
```

If an error is present, the status is set to `PROCESSING_ERROR`; otherwise, it is set to `PROCESSED`.

Update the database with the transcription results and the processing status:

```py
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
```

This finds the document in the database with the matching `replicate_process_id` and updates it with the new status, transcription `text`, and the entire payload.

If the document wasn't found, log an error and return a `404` response:

```py
    if result is None:
        app.logger.error(
            "No document found for id %s to add audio transcript", payload["id"]
        )
        return jsonify({"error": "No document found to add audio transcript"}), 404
```

If no document is found for the given `replicate_process_id`, an error is logged, and a JSON response with an error message is returned. The `404` response will inform Hookdeck that although the request did not succeed, the request should not be retried.

With the audio converted to text and stored, the data journey moves to generating embeddings via Replicate:

```py
    app.logger.info("Transcription updated")
    app.logger.debug(result)

    request_embeddings(result["_id"])

    return "OK"
```

This code logs that the transcription has been updated and calls the `request_embeddings` function to generate embeddings for the processed audio. The endpoint returns an `OK` response to inform Hookdeck the webhook has been successfully processed.

In summary, this route updates the database with transcription results and requests embeddings for the processed audio.

## H2: Generate Embedding

The `request_embeddings` function triggers the generation of embeddings for the textual representation of any indexed assets.

Begin by retrieving the asset representation from MongoDB:

```py
def request_embeddings(id):
    app.logger.info("Requesting embeddings for %s", id)

    database = Database()
    collection = database.get_collection()

    asset = collection.find_one({"_id": id})

    if asset is None:
        raise RuntimeError("Asset not found")
```

This code finds the document in the database with the matching ID. If no document is found, a `RuntimeError` is raised.

Check if the asset has been processed:

```py
    if asset["status"] != "PROCESSED":
        raise RuntimeError("Asset has not been processed")
```

This code checks if the status of the asset is `PROCESSED`, indicating that a textual representation has been created. If the asset has not been processed, a `RuntimeError` is raised.

### H3: Trigger Embedding Generation with Webhook Callback

Next, generate the embeddings for the processed asset using the `AsyncEmbeddingsGenerator`:

```py
    generator = AsyncEmbeddingsGenerator()

    generate_request = generator.generate(asset["text"])
```

This code initializes the `AsyncEmbeddingsGenerator` and calls the `generate` function on the instance, passing the textual representation of the asset.

The `AsyncEmbeddingsGenerator` definition in `allthethings/generators.py` follows a similar pattern to the previously used processor:

```py
import replicate
from config import Config

class AsyncEmbeddingsGenerator:
    def __init__(self):
        self.WEBHOOK_URL = Config.EMBEDDINGS_WEBHOOK_URL
        self.model = replicate.models.get("replicate/all-mpnet-base-v2")
        self.version = self.model.versions.get(
            "b6b7585c9640cd7a9572c6e129c9549d79c9c31f0d3fdce7baac7c67ca38f305"
        )
```

This class initializes the `AsyncEmbeddingsGenerator` with the `EMBEDDINGS_WEBHOOK_URL` webhook URL passed to receive the asynchronous response. The [replicate/all-mpnet-base-v2](replicate/all-mpnet-base-v2) model us used to generate embeddings.

Next, the `generate` method within the `AsyncEmbeddingsGenerator` class:

```py
    def generate(self, text):
        input = {"text": text}

        prediction = replicate.predictions.create(
            version=self.version,
            input=input,
            webhook=self.WEBHOOK_URL,
            webhook_events_filter=["completed"],
        )

        return prediction
```

This method generates embeddings for the provided text by creating a prediction request to the Replicate model. As before, the use of the `webhook_events_filter=["completed"]` filter informs Replicate to only send a webhook when the prediction is completed. The method returns the prediction object, which contains the details of the embedding generation request.

Back in `app.py`, update the database with the status and embedding request ID:

```py
    collection.update_one(
        filter={"_id": id},
        update={
            "$set": {
                "status": "GENERATING_EMBEDDINGS",
                "replicate_embedding_id": generate_request.id,
            }
        },
    )
```

Update the document in the database with the new status `GENERATING_EMBEDDINGS` and the ID of the embedding request.

The request to asynchronously generate the embeddings has been triggered, and the work offloaded to Replicate. When the result is read, a webhook will be triggered with the result.

### H3: Handle Embedding Generation Webhook Callback

### Step 16: Handling Embedding Webhooks

The `/webhooks/embedding` route in our Flask application handles the webhooks for embedding generation. This route receives the webhook payload, updates the database with the embedding results, and sets the appropriate status.

First, the `/webhooks/embedding` route definition:

```py
@app.route("/webhooks/embedding", methods=["POST"])
def webhook_embeddings():
    payload = request.json
    app.logger.info("Embeddings payload received")
    app.logger.debug(payload)
```

This route handles POST requests to the `/webhooks/embedding` endpoint. It retrieves the JSON payload from the request.

Determine the processing status based on the presence of an error in the payload:

```py
    status = (
        "EMBEDDINGS_ERROR" if "error" in payload and payload["error"] else "SEARCHABLE"
    )
```

This code checks if there is an error in the payload. If an error is present, the status is set to `EMBEDDINGS_ERROR`; otherwise, it is set to `SEARCHABLE`.

Next, extract the vector embedding from the payload and update the database with the embedding details and the new status:

```py
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
```

This finds the document in the database with the matching `replicate_embedding_id` and updates it with the new status, embedding, and the entire payload.

Check if the document was found and updated:

```py
    if result.matched_count == 0:
        app.logger.error(
            "No document found for id %s to update embedding", payload["id"]
        )
        return jsonify({"error": "No document found to update embedding"}), 404

    return "OK"
```

If no document is found for the given `replicate_embedding_id`, an error is logged, and a JSON response with an error message is returned with a `404` status. If the update was success, return an `OK` to inform Hookdeck the webhook has been processed.

With the vector embedding stored in the `embedding` property, it's now searchable with MongoDB due to the previously defined vector search index.

## H2: Searching using Atlas Vector Search

Search is user-driven. The user enters a search term and submits a form. That search query is handled, processed and the resulted returned and displayed. Let's walk through through each of those steps.

![Search results](<search-results.png)

### H3: Handle Search Submission

The user navigates to the `/search` endpoint in their web browser, enters a search term and submits the form, making a `POST` request to the `/search` endpoint:

```py
@app.route("/search", methods=["POST"])
def search_post():
    query = request.form["query"]

    app.logger.info("Query submitted")
    app.logger.debug(query)

    results = query_vector_search(query)

    results = format_results(results)

    app.logger.debug("Formatted search results", results)

    return render_template("search.html", results=results, query=query)
```

The `search_post` function in the Flask application handles `POST` requests to the `/search` endpoint. It retrieves the search `query` from the form data submitted by the user and then performs a vector search using the `query_vector_search` function. The result is then formatted by passing the results to the `format_results` function. The formatted results are then rendered using the `search.html` template.

The `query_vector_search` function performs a vector search using the query provided by the user, generates embeddings for the query, and retrieves matching documents from the MongoDB collection.

```py
def query_vector_search(q):
```

### H3: Generating Search Query Embeddings

The function uses the `SyncEmbeddingsGenerator` to generate the embedding for the search query.

```py
    generator = SyncEmbeddingsGenerator()
    generate_response = generator.generate(q)
    query_embedding = generate_response[0]["embedding"]

    app.logger.info("Query embedding generated")
    app.logger.debug(query_embedding)
```

The `SyncEmbeddingsGenerated` is used to synchronously generate embeddings for the search query. This operation is synchronous because the request is user-driven and requires a direct response. `SyncEmbeddingsGenerated` is defined in `allthethings/generators.py`:

```py
class SyncEmbeddingsGenerator:

    def generate(self, text):

        input = {"text": text}
        output = replicate.run(
            "replicate/all-mpnet-base-v2:b6b7585c9640cd7a9572c6e129c9549d79c9c31f0d3fdce7baac7c67ca38f305",
            input=input,
        )

        return output
```

The Replicate SDK is used to synchronously generate the embedding using the same model as the asynchronous generator. The result is returned to the calling `query_vector_search` function.

### H3. Create Vector Search Query

Back in `query_vector_search`, the embedding result is used to construct the vector search query.

```py
    generator = SyncEmbeddingsGenerator()
    generate_response = generator.generate(q)
    query_embedding = generate_response[0]["embedding"]

    vs_query = {
        "index": "vector_index",
        "path": "embedding",
        "queryVector": query_embedding,
        "numCandidates": 10,
        "limit": topK,
    }

    new_search_query = {"$vectorSearch": vs_query}

    app.logger.info("Vector search query created")
    app.logger.debug(new_search_query)
```

TODO: describe vs_query

H3: Retrieve Vector Search Results

Next, the function defines the projection to specify which fields to include in the search results.

```py
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
```

The projection includes the vector search score, URL, content type, content length, and text.

The function then performs the aggregation query using the constructed vector search query and projection:

```py
    database = Database()
    collection = database.get_collection()

    app.logger.info("Vector search query without post filter")
    res = list(collection.aggregate([new_search_query, project]))

    app.logger.info("Vector search query run")
    app.logger.debug(res)
    return res
```

Overall, the `query_vector_search` function performs a vector search using the query provided by the user, generates embeddings for the query, and retrieves matching documents from the MongoDB collection.

#### H3. Format and Display the Vector Search Results

Once the results are available they are formatted for rendering:

```py
    results = format_results(results)
```

And within `format_results`, also defined in `app.py`:

```py
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
```

The `format_results` function iterates over the vector search result and returns and array with each element containing the result along with a `parsed_url` property with information about the indexed asset.

Finally, back in the `POST /search` route, display the results:

```py
@app.route("/search", methods=["POST"])
def search_post():
    ...

    results = format_results(results)

    return render_template("search.html", results=results, query=query)
```

This renders the `search.html` template, passing the formatted results and the original query to the template for display.

## H2: Conclusion




