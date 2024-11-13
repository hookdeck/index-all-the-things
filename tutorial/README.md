# Index All the Things: Using Replicate, MongoDB, and Hookdeck to Build Scalable Content Type Agnostic Vector Search with Python and Flask

## Introduction

In this tutorial, we will explore how to build a scalable, content-type agnostic vector search application using Python and Flask. We will leverage Replicate for model inference, MongoDB for data storage, and Hookdeck for managing webhooks.

One of the key features of this vector search solution is its content-type agnosticism. This means that the app is designed to analyze and index various types of content but will use the textual representation as the common denominator. The current application supports HTML and Audio only. However, you will see how it can be expanded to support other content types.

In this guide, we'll begin by getting an application up and running and then we'll follow the journey of data through key components and code within the app as it's analyzed, transformed, and enriched. We'll submit a piece of content to be indexed, it's content-type analyzed, an embedding is generated and stored, and the content is ultimately made available for search within a vector search index.

## Architecture Overview

Scalability is often overhyped, but it remains an important aspect of building robust applications. One of the benefits of using serverless and cloud-hosted providers is the ability to offload work to specialized services. In this tutorial, we leverage several such services to handle different aspects of our application:

- **Replicate**: Handles AI inference, producing text and embeddings and allowing us to offload the computationally intensive tasks of running machine learning models.
- **MongoDB**: Provides database storage and vector search capabilities, ensuring our data is stored efficiently and can be queried quickly.
- **Hookdeck**: Acts as a serverless queue, managing webhooks and ensuring reliable communication between services. It also provides a CLI, enabling you to receive webhooks in your local development environment.


TODO: image

By utilizing these cloud-based services, we can focus on building the core functionality of our application while ensuring it remains scalable and efficient. Webhooks, in particular, allow for scalability by enabling [asynchronous AI workflows](https://hookdeck.com/blog/asynchronous-ai?ref=mongodb-iatt), offloading those high compute usage scenarios to the third-party services, and just receiving callbacks via a webhook when work is completed.

## Prerequisites

Before you begin, ensure you have the following:

- A free [Hookdeck account](https://dashboard.hookdeck.com/signup?ref=mongodb-iatt)
- The [Hookdeck CLI installed](https://hookdeck.com/docs/cli?ref=mongodb-iatt)
- A trial [MongoDB Atlas account](https://www.mongodb.com/cloud/atlas/register)
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
- `REPLICATE_API_TOKEN`: [Create an API token](https://replicate.com/account/api-tokens).
- `AUDIO_WEBHOOK_URL` and `EMBEDDINGS_WEBHOOK_URL` will be automatically populated in the next step.

### H3: Create Hookdeck Connections

The `create-hookdeck-connections.py` script automatically creates [Hookdeck Connections](https://hookdeck.com/docs/connections?ref=mongodb-iatt) that route requests made to Hookdeck URLs through to the locally running application. It also updates the `.env`
file with the new webhook URLs.

First, ensure you have the necessary imports and define the headers for the Hookdeck API request:

```py
import http.client
import json
from config import Config
import re

# Define the headers for the Hookdeck API request
headers = {
    "Authorization": f"Bearer {Config.HOOKDECK_PROJECT_API_KEY}",
    "Content-Type": "application/json",
}
```

Next, define a function to create a connection to the Hookdeck API:

```py
def create_connection(payload):
    conn = http.client.HTTPSConnection("api.hookdeck.com")
    conn.request(
        "PUT", "/latest/connections", body=json.dumps(payload), headers=headers
    )
    response = conn.getresponse()
    data = response.read().decode()
    conn.close()

    if response.status != 200:
        raise Exception(f"Failed to create connection: {data}")

    return json.loads(data)
```

This function establishes a connection to the Hookdeck API, sends a PUT request with the [upsert connection payload](https://hookdeck.com/docs/api#createupdate-a-connection?ref=mongodb-iatt), and handles the response. If the response status is not `200` (OK), an exception is raised. The function returns the parsed JSON response.

Now, create a connection for "replicate-audio" to handle audio analysis callbacks:

```py
replicate_audio = {
    "name": "replicate-audio",
    "source": {
        "name": "replicate-audio",
    },
    "destination": {
        "name": "cli-replicate-audio",
        "cli_path": "/webhooks/audio",
    },
}

replicate_audio_connection = create_connection(replicate_audio)
```

Next, create a connection for "replicate-embedding" to handle embedding generation callbacks:

```py
replicate_embedding = {
    "name": "replicate-embedding",
    "source": {
        "name": "replicate-embedding",
    },
    "destination": {
        "name": "cli-replicate-embedding",
        "cli_path": "/webhooks/embedding",
    },
}

replicate_embedding_connection = create_connection(replicate_embedding)
```

Finally, update the `.env` file with the new webhook URLs obtained from the API responses:

```py
# Update .env
with open(".env", "r") as file:
    env_content = file.read()

audio_webhook_url = replicate_audio_connection["source"]["url"]
embedding_webhook_url = replicate_embedding_connection["source"]["url"]

# Replace the webhooks URLs in the .env content
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
```

This code reads the current `.env` content, replaces the existing `AUDIO_WEBHOOK_URL` and `EMBEDDINGS_WEBHOOK_URL` using regular expressions, and writes the updated content back to the `.env` file. This ensures that the environment variables for the webhook URLs are up-to-date.

Run the script:

```sh
poetry run python create-hookdeck-connections.py
```

Check your `.env` file to ensure the `...WEBHOOK_URL` values are populated.

Also, navigate to the **Connections** section of the Hookdeck dashboard and check the visual representation of your connection.

TODO: Image

### H3: Create MongoDB Atlas Indexes

In order to efficiently search a MongoDB database you need indexes. For MongoDB vector search you must create an [Atlas Vector Search Index](https://www.mongodb.com/docs/atlas/atlas-vector-search/vector-search-overview/#atlas-vector-search-indexes). The `create-indexes.py` script automates the creation and updating of the search indexes in MongoDB using the `pymongo` library.

First, ensure you have the necessary imports and initialize the database connection:

```py
from allthethings.mongo import Database
from pymongo.operations import SearchIndexModel

database = Database()
collection = database.get_collection()
```

Next, define a function to create or update search indexes:

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
        result = collection.create_search_index(model=index_model)
    else:
        print(f'Search index "{index_name}" already exists. Updating.')
        result = collection.update_search_index(
            name=index_name, definition=index_definition
        )
    return result
```

This function checks if an index with the given name (`index_name`) already exists. If it does not exist, it creates a new search index using the provided definition and type. If it exists, it updates the existing index with the new definition.

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
print(vector_result)
```

This code creates or updates a vector search index named "vector_index" with fields for embeddings, specifying the number of dimensions and similarity measure.

Finally, create a search index for `replicate_embedding_id` because it's used when looking up documents when storing embedding results:

```py
index_result = create_or_update_search_index(
    "replicate_by_embedding_id_index",
    {
        "mappings": {"dynamic": True},
        "fields": [
            {
                "type": "string",
                "path": "replicate_embedding_id",
            }
        ],
    },
    "search",
)
print(index_result)
```

This code creates or updates a search index named "replicate_by_embedding_id_index" with fields for `replicate_embedding_id`.

Run the script:

```sh
poetry run python create-hookdeck-connections.py
```

H3: Check the App is Working
H2: Submit Content for Analysis and Indexing
H3: Detect Content-Type
H3: Store Progress
H2: Analyze Content
H3: Trigger Prediction with Webhook Callback
H3: Handle Prediction Completion Webhook
H3: Store Progress
H2: Generate Embedding
H3: Trigger Embedding Generation with Webhook Callback
H3: Handle Embedding Generation Webhook Callback
H3: Store Embedding
H3: Store Progress
H2: Searching using Atlas Vector Search
H3: Handle Search Submission
H3: Generate Search Query Embedding
H3: Retrieve Vector Search Results
H2: Conclusion


