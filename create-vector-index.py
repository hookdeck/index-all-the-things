# Inspiration https://www.mongodb.com/developer/products/atlas/how-use-cohere-embeddings-rerank-modules-mongodb-atlas/#programmatically-create-vector-search-and-full-text-search-index

from lib.mongo import get_mongo_client
from pymongo.operations import SearchIndexModel
from dotenv import load_dotenv

load_dotenv()

DB_NAME = "iaat"
COLLECTION_NAME = "assets"

# Connect to your Atlas deployment
client = get_mongo_client()
if client is None:
    raise Exception("Failed to connect to MongoDB")

# Access your database and collection
database = client[DB_NAME]
collection = database[COLLECTION_NAME]

# Create your index model, then create the search index
search_index_model = SearchIndexModel(
    definition={
        "fields": [
            {
                "type": "vector",
                "path": "embedding",
                "numDimensions": 768,
                "similarity": "euclidean",
            }
        ]
    },
    name="vector_index",
    type="vectorSearch",
)

result = collection.create_search_index(model=search_index_model)
print(result)
