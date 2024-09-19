from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi

from config import Config


def get_mongo_client():
    MONGODB_CONNECTION_URI = Config.MONGODB_CONNECTION_URI

    # Create a new client and connect to the server
    client = MongoClient(MONGODB_CONNECTION_URI, server_api=ServerApi("1"))

    # Send a ping to confirm a successful connection
    try:
        client.admin.command("ping")
        print("Pinged your deployment. You successfully connected to MongoDB!")
        return client
    except Exception as e:
        print(e)
        return None
