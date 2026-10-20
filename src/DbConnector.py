from pymongo import MongoClient, version
import dotenv
from urllib.parse import quote_plus

class DbConnector:
    """
    Connects to the MongoDB server on the Ubuntu virtual machine.
    Connector needs HOST, USER and PASSWORD to connect.

    Example:
    HOST = "tdt4225-00.idi.ntnu.no" // Your server IP address/domain name
    USER = "testuser" // This is the user you created and added privileges for
    PASSWORD = "test123" // The password you set for said user
    """
    dotenv.load_dotenv()

    def __init__(self,
                 DATABASE=dotenv.get_key('.env', 'DATABASE'),
                 HOST=dotenv.get_key('.env', 'HOST'),
                 USER=dotenv.get_key('.env', 'USER'),
                 PASSWORD=dotenv.get_key('.env', 'PASSWORD')):
        USER = quote_plus(USER)
        PASSWORD = quote_plus(PASSWORD)
        HOST = quote_plus(HOST)
        DATABASE = quote_plus(DATABASE)
        uri = "mongodb://%s:%s@%s/%s" % (USER, PASSWORD, HOST, DATABASE)
        # Connect to the databases
        try:
            self.client = MongoClient(uri)
            self.db = self.client[DATABASE]
        except Exception as e:
            print("ERROR: Failed to connect to db:", e)

        # get database information
        print("You are connected to the database:", self.db.name)
        print("-----------------------------------------------\n")

    def close_connection(self):
        # close the cursor
        # close the DB connection
        self.client.close()
        print("\n-----------------------------------------------")
        print("Connection to %s-db is closed" % self.db.name)
