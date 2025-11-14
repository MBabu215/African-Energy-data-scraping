# upload_to_mongo.py
import os, pandas as pd
from dotenv import load_dotenv
from pymongo import MongoClient
from tqdm import tqdm

CSV_PATH = "aep_preprocessed_wide_2000_2022.csv"

def upload():
    load_dotenv()
    MONGO_URI = os.getenv("MONGO_URI")
    MONGO_DB = os.getenv("MONGO_DB", "aep_database")
    MONGO_COLLECTION = os.getenv("MONGO_COLLECTION", "aep_data")

    if not MONGO_URI:
        raise ValueError("Missing MONGO_URI in .env file")

    client = MongoClient(MONGO_URI)
    db = client[MONGO_DB]
    collection = db[MONGO_COLLECTION]
    print(f"Connected to MongoDB: {MONGO_DB}.{MONGO_COLLECTION}")

    print("Reading CSV file...")
    df = pd.read_csv(CSV_PATH)
    df = df.where(pd.notnull(df), None)

    collection.delete_many({})
    print("Cleared existing collection")

    records = df.to_dict("records")
    batch_size = 1000
    for i in tqdm(range(0, len(records), batch_size)):
        batch = records[i:i + batch_size]
        collection.insert_many(batch)
    print(f"✅ Inserted {len(records)} records into MongoDB")

    count = collection.count_documents({})
    print(f"Collection now contains {count} documents")
    client.close()

if __name__ == "__main__":
    upload()
