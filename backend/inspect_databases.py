import asyncio
from app.core.database import client


async def main():
    collections = [
        "users",
        "articles",
        "categories",
        "tags",
        "media",
        "notifications",
        "web_stories",
        "web_story_events",
        "writer_applications",
        "activation_tokens",
        "settings",
    ]

    for db_name in ["cms_db", "dorecord_cms_db"]:
        db = client[db_name]

        print("\n" + "=" * 80)
        print(f" DATABASE: {db_name}")
        print("=" * 80)

        existing_collections = await db.list_collection_names()

        for collection in collections:
            if collection not in existing_collections:
                continue

            documents = await db[collection].find(
                {},
                {"password": 0}
            ).to_list(length=50)

            print(f"\n--- {collection} ({len(documents)}) ---")

            for document in documents:
                print(document)


if __name__ == "__main__":
    asyncio.run(main())