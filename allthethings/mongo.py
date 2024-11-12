from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi

from config import Config


class Database:

    def __init__(self):
        MONGODB_CONNECTION_URI = Config.MONGODB_CONNECTION_URI

        self.client = MongoClient(MONGODB_CONNECTION_URI, server_api=ServerApi("1"))

        self.client.admin.command("ping")

    def get_client(self):
        return self.client

    def get_collection(self):
        return self.client.get_database(Config.DB_NAME).get_collection(
            Config.COLLECTION_NAME
        )
