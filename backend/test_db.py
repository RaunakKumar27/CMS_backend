import asyncio
from app.core.database import client


async def show_collection(database_name, collection_name):
    database = client[database_name]

    documents = await database[collection_name].find(
        {},
        {"password": 0}
    ).to_list(length=100)

    print(f"\n===== {database_name}.{collection_name} =====")
    print("Documents:", len(documents))

    for document in documents:
        print(document)


async def main():
    for collection in [
        "users",
        "categories",
        "tags",
        "articles",
        "settings"
    ]:
        await show_collection("cms_db", collection)
        await show_collection("dorecord_cms_db", collection)


asyncio.run(main())