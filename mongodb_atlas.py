from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
from bson.objectid import ObjectId
import os

# 🔗 替換成你的 MongoDB Atlas 連線字串
MONGO_PASSWORD = os.getenv("MONGO_PASSWORD")
MONGO_URI = f"mongodb+srv://koyingchen0523:{MONGO_PASSWORD}@cluster0.455wa.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
DB_NAME = "test_database"
COLLECTION_NAME = "testing"

# 🚀 建立 MongoDB 連線
def connect_to_mongodb():
    try:
        client = MongoClient(MONGO_URI)
        client.admin.command('ping')  # 測試連線
        print("✅ 成功連接到 MongoDB Atlas")
        return client
    except ConnectionFailure as e:
        print("🚨 連接 MongoDB 失敗:", e)
        return None

def insert_one(collection, data):
    result = collection.insert_one(data)
    return result.inserted_id

# 🎯 插入單筆資料
def insert_one_document(collection):
    user = {"name": "Alice", "age": 25, "city": "New York"}
    result = collection.insert_one(user)
    print(f"✅ 插入成功, ID: {result.inserted_id}")

# 🎯 插入多筆資料
def insert_many_documents(collection):
    users = [
        {"name": "Bob", "age": 30, "city": "Los Angeles"},
        {"name": "Charlie", "age": 35, "city": "Chicago"},
        {"name": "David", "age": 40, "city": "Miami"},
    ]
    result = collection.insert_many(users)
    print(f"✅ 插入 {len(result.inserted_ids)} 筆資料")

def find_one(collection, query):
    return collection.find_one(query)

def delete_one(collection, query):
    return collection.delete_one(query)

# 🔍 查詢單筆資料
def find_one_document(collection):
    user = collection.find_one({"name": "Alice"})
    print("🔍 查詢結果:", user)

# 🔍 查詢多筆資料
def find_many_documents(collection):
    users = collection.find({"age": {"$gte": 30}})
    print("📃 符合條件的用戶:")
    for user in users:
        print(user)

# ✏️ 更新單筆資料
def update_one_document(collection):
    result = collection.update_one({"name": "Alice"}, {"$set": {"age": 26}})
    print(f"✅ 更新 {result.modified_count} 筆資料")

# ✏️ 更新多筆資料
def update_many_documents(collection):
    result = collection.update_many({"city": "Chicago"}, {"$set": {"city": "San Francisco"}})
    print(f"✅ 更新 {result.modified_count} 筆資料")

# 🗑️ 刪除單筆資料
def delete_one_document(collection):
    result = collection.delete_one({"name": "Charlie"})
    print(f"✅ 刪除 {result.deleted_count} 筆資料")

# 🗑️ 刪除多筆資料
def delete_many_documents(collection):
    result = collection.delete_many({"age": {"$gte": 40}})
    print(f"✅ 刪除 {result.deleted_count} 筆資料")

# 📌 建立索引 (提升查詢效能)
def create_index(collection):
    index_name = collection.create_index("age")
    print(f"✅ 建立索引: {index_name}")

# 📊 聚合查詢 (分組 & 統計)
def aggregate_documents(collection):
    pipeline = [
        {"$group": {"_id": "$city", "total_users": {"$sum": 1}}}
    ]
    results = collection.aggregate(pipeline)
    print("📊 城市用戶統計:")
    for result in results:
        print(result)

# 🚀 主函式
if __name__ == "__main__":
    client = connect_to_mongodb()
    if client:
        db = client[DB_NAME]
        collection = db[COLLECTION_NAME]

        insert_one_document(collection)  # 插入單筆
        insert_many_documents(collection)  # 插入多筆
        find_one_document(collection)  # 查詢單筆
        find_many_documents(collection)  # 查詢多筆
        update_one_document(collection)  # 更新單筆
        update_many_documents(collection)  # 更新多筆
        delete_one_document(collection)  # 刪除單筆
        delete_many_documents(collection)  # 刪除多筆
        create_index(collection)  # 建立索引
        aggregate_documents(collection)  # 聚合查詢

        # 🚪 關閉連線
        client.close()
        print("🔌 MongoDB 連線已關閉")
