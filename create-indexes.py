# Inspiration https://www.mongodb.com/developer/products/atlas/how-use-cohere-embeddings-rerank-modules-mongodb-atlas/#programmatically-create-vector-search-and-full-text-search-index

from allthethings.mongo import Database
from pymongo.operations import SearchIndexModel

database = Database()
collection = database.get_collection()

if collection.name not in collection.database.list_collection_names():
    print("Creating empty collection so indexes can be created.")
    collection.database.create_collection(collection.name)


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


create_or_update_search_index(
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
