# Inspiration https://www.mongodb.com/developer/products/atlas/how-use-cohere-embeddings-rerank-modules-mongodb-atlas/#programmatically-create-vector-search-and-full-text-search-index

from allthethings.mongo import Database
from pymongo.operations import SearchIndexModel

database = Database()
collection = database.get_collection()

search_index_name = "vector_index"
search_index_definition = {
    "fields": [
        {
            "type": "vector",
            "path": "embedding",
            "numDimensions": 768,
            "similarity": "euclidean",
        }
    ]
}

if collection.list_search_indexes(search_index_name) is not None:
    print(f'Creating search index: "{search_index_name}"')
    search_index_model = SearchIndexModel(
        definition=search_index_definition,
        name=search_index_name,
        type="vectorSearch",
    )
    result = collection.create_search_index(model=search_index_model)

else:
    print(f'Search index "{search_index_name}" already exists. Updating.')
    result = collection.update_search_index(
        name=search_index_name, definition=search_index_definition
    )

print(result)
