from copy import deepcopy
from datetime import datetime
from bson import ObjectId
from pymongo import MongoClient


# ============================================================
# CONFIGURATION
# ============================================================

# IMPORTANT:
# This script intentionally connects ONLY to local MongoDB.
LOCAL_MONGO_URI = "mongodb://localhost:27017"

SOURCE_DBS = [
    "cms_db",
    "dorecord_cms_db",
]

TARGET_DB = "dorecord_merged"


# ============================================================
# HELPERS
# ============================================================

def new_id():
    return ObjectId()


def get_documents(db, collection_name):
    return list(db[collection_name].find({}))


def safe_insert(collection, document):
    """
    Insert document.
    If an _id already exists in target, generate a new one.
    """
    if "_id" in document:
        if collection.find_one({"_id": document["_id"]}):
            document["_id"] = new_id()

    collection.insert_one(document)
    return document["_id"]


# ============================================================
# CONNECT TO LOCAL MONGODB
# ============================================================

print()
print("=" * 70)
print("DO RECORD DATABASE MERGE")
print("=" * 70)

print("\nConnecting to LOCAL MongoDB...")
print("URI:", LOCAL_MONGO_URI)

client = MongoClient(
    LOCAL_MONGO_URI,
    serverSelectionTimeoutMS=5000
)

try:
    client.admin.command("ping")
    print("Local MongoDB connection: OK")
except Exception as error:
    print("\nERROR: Could not connect to local MongoDB.")
    print(error)
    raise SystemExit(1)


db1 = client["cms_db"]
db2 = client["dorecord_cms_db"]


# ============================================================
# CREATE / RESET TARGET DATABASE
# ============================================================

print("\nTarget database:", TARGET_DB)

if TARGET_DB in client.list_database_names():
    print("Target already exists.")
    print("Clearing ONLY:", TARGET_DB)

    client.drop_database(TARGET_DB)

target = client[TARGET_DB]

print("Target database ready.")


# ============================================================
# 1. USERS
# ============================================================

print("\n" + "=" * 70)
print("1. USERS")
print("=" * 70)

users1 = get_documents(db1, "users")
users2 = get_documents(db2, "users")

all_users = users1 + users2


# ---------- Select Super Admin ----------

super_admin = None

# Prefer admin from dorecord_cms_db
for user in users2:
    if (
        user.get("username") == "admin"
        and user.get("role") == "super_admin"
        and user.get("is_active") is True
    ):
        super_admin = deepcopy(user)
        break


if super_admin is None:
    for user in all_users:
        if (
            user.get("role") == "super_admin"
            and user.get("is_active") is True
        ):
            super_admin = deepcopy(user)
            break


if super_admin is None:
    raise RuntimeError("No active Super Admin found.")


# ---------- Select Rounak Writer ----------

writer = None

for user in users1 + users2:
    if (
        user.get("email") == "rounaksingh2710@gmail.com"
        and user.get("role") == "writer"
        and user.get("is_active") is True
    ):
        writer = deepcopy(user)
        break


if writer is None:
    for user in users1 + users2:
        if (
            user.get("username") == "rounak_singh"
            and user.get("role") == "writer"
        ):
            writer = deepcopy(user)
            break


if writer is None:
    raise RuntimeError("Rounak writer account not found.")


# ---------- Generate new IDs ----------

new_super_admin_id = new_id()
new_writer_id = new_id()

super_admin["_id"] = new_super_admin_id
writer["_id"] = new_writer_id

super_admin["role"] = "super_admin"
super_admin["is_active"] = True

writer["role"] = "writer"
writer["is_active"] = True


# Insert exactly 2 users

target["users"].insert_many([
    super_admin,
    writer
])


print("Super Admin:")
print("  username:", super_admin.get("username"))
print("  email:", super_admin.get("email"))

print("Writer:")
print("  username:", writer.get("username"))
print("  email:", writer.get("email"))


# ---------- Build old user ID mapping ----------

old_super_admin_ids = set()
old_writer_ids = set()

for user in all_users:

    user_id = str(user["_id"])

    if user.get("role") == "super_admin":
        old_super_admin_ids.add(user_id)

    else:
        old_writer_ids.add(user_id)


# Rounak IDs are definitely writer IDs
for user in all_users:
    if user.get("email") == "rounaksingh2710@gmail.com":
        old_writer_ids.add(str(user["_id"]))


print("\nOld Super Admin IDs:", len(old_super_admin_ids))
print("Old Writer/User IDs:", len(old_writer_ids))


# ============================================================
# 2. CATEGORIES
# ============================================================

print("\n" + "=" * 70)
print("2. CATEGORIES")
print("=" * 70)

categories1 = get_documents(db1, "categories")
categories2 = get_documents(db2, "categories")

categories_by_slug = {}

for category in categories1 + categories2:

    slug = category.get("slug")

    if not slug:
        continue

    if slug not in categories_by_slug:
        categories_by_slug[slug] = deepcopy(category)


category_id_map = {}
category_name_by_new_id = {}

for slug, category in categories_by_slug.items():

    old_id = str(category["_id"])

    new_category_id = new_id()

    category_id_map[old_id] = str(new_category_id)

    category["_id"] = new_category_id

    category_name_by_new_id[str(new_category_id)] = (
        category.get("name", slug)
    )

    target["categories"].insert_one(category)


print("Categories copied:", len(categories_by_slug))

for slug in sorted(categories_by_slug):
    print("  -", slug)


# ============================================================
# 3. TAGS
# ============================================================

print("\n" + "=" * 70)
print("3. TAGS")
print("=" * 70)

tags1 = get_documents(db1, "tags")
tags2 = get_documents(db2, "tags")

tags_by_slug = {}

for tag in tags1 + tags2:

    slug = tag.get("slug")

    if not slug:
        continue

    if slug not in tags_by_slug:
        tags_by_slug[slug] = deepcopy(tag)


for tag in tags_by_slug.values():
    tag["_id"] = new_id()


if tags_by_slug:
    target["tags"].insert_many(
        list(tags_by_slug.values())
    )


print("Tags copied:", len(tags_by_slug))


# ============================================================
# 4. ARTICLES
# ============================================================

print("\n" + "=" * 70)
print("4. ARTICLES")
print("=" * 70)

articles1 = get_documents(db1, "articles")
articles2 = get_documents(db2, "articles")

all_articles = []

for source_name, source_db in [
    ("cms_db", db1),
    ("dorecord_cms_db", db2),
]:

    source_articles = get_documents(
        source_db,
        "articles"
    )

    for article in source_articles:

        article = deepcopy(article)

        # -------------------------------
        # CATEGORY
        # -------------------------------

        old_category_id = str(
            article.get("category_id", "")
        )

        if old_category_id in category_id_map:

            new_category_id = category_id_map[
                old_category_id
            ]

            article["category_id"] = new_category_id

            article["category_name"] = (
                category_name_by_new_id.get(
                    new_category_id,
                    article.get("category_name")
                )
            )

        # -------------------------------
        # AUTHOR
        # -------------------------------

        old_author_id = str(
            article.get("author_id", "")
        )

        if old_author_id in old_super_admin_ids:

            article["author_id"] = str(
                new_super_admin_id
            )

            article["author_name"] = (
                super_admin.get(
                    "name",
                    "Super Admin"
                )
            )

            article["author_avatar"] = (
                super_admin.get("avatar_url")
            )

        else:

            # Only one writer is retained.
            # All old writer accounts are mapped
            # to the retained Rounak writer.

            article["author_id"] = str(
                new_writer_id
            )

            article["author_name"] = (
                writer.get(
                    "name",
                    "Rounak Kumar"
                )
            )

            article["author_avatar"] = (
                writer.get("avatar_url")
            )

        all_articles.append(article)


# Insert articles

article_ids = set()

for article in all_articles:

    article_id = str(article["_id"])

    if article_id in article_ids:
        article["_id"] = new_id()

    article_ids.add(str(article["_id"]))

    target["articles"].insert_one(article)


print("Articles copied:", len(all_articles))


# ============================================================
# 5. MEDIA
# ============================================================

print("\n" + "=" * 70)
print("5. MEDIA")
print("=" * 70)

media_documents = []

for source_db in [db1, db2]:

    for media in get_documents(
        source_db,
        "media"
    ):

        media = deepcopy(media)

        uploaded_by = str(
            media.get("uploaded_by_id", "")
        )

        if uploaded_by in old_super_admin_ids:

            media["uploaded_by_id"] = str(
                new_super_admin_id
            )

        elif uploaded_by in old_writer_ids:

            media["uploaded_by_id"] = str(
                new_writer_id
            )

        media_documents.append(media)


media_ids = set()

for media in media_documents:

    media_id = str(media["_id"])

    if media_id in media_ids:
        media["_id"] = new_id()

    media_ids.add(str(media["_id"]))

    target["media"].insert_one(media)


print("Media copied:", len(media_documents))


# ============================================================
# 6. WEB STORY
# ============================================================

print("\n" + "=" * 70)
print("6. WEB STORIES")
print("=" * 70)

stories2 = get_documents(
    db2,
    "web_stories"
)

stories1 = get_documents(
    db1,
    "web_stories"
)

all_stories = stories2 + stories1

selected_story = None

if all_stories:
    # There is currently one story, so keep it.
    selected_story = deepcopy(all_stories[0])


story_id_map = {}

if selected_story:

    old_story_id = str(
        selected_story["_id"]
    )

    new_story_id = new_id()

    story_id_map[old_story_id] = str(
        new_story_id
    )

    selected_story["_id"] = new_story_id

    # Category
    old_category_id = str(
        selected_story.get(
            "category_id",
            ""
        )
    )

    if old_category_id in category_id_map:

        selected_story["category_id"] = (
            category_id_map[
                old_category_id
            ]
        )

    # Story author
    selected_story["author_id"] = str(
        new_super_admin_id
    )

    selected_story["author_name"] = (
        super_admin.get(
            "name",
            "Super Admin"
        )
    )

    selected_story["author_avatar"] = (
        super_admin.get("avatar_url")
    )

    target["web_stories"].insert_one(
        selected_story
    )

    print(
        "Kept Web Story:",
        selected_story.get(
            "title",
            "Untitled"
        )
    )

else:

    print("No web story found.")


# ============================================================
# 7. WEB STORY EVENTS
# ============================================================

print("\n" + "=" * 70)
print("7. WEB STORY EVENTS")
print("=" * 70)

events_to_copy = []

if selected_story:

    original_story_id = next(
        iter(story_id_map.keys())
    )

    new_story_id = story_id_map[
        original_story_id
    ]

    for source_db in [db1, db2]:

        events = get_documents(
            source_db,
            "web_story_events"
        )

        for event in events:

            if str(
                event.get("story_id")
            ) == original_story_id:

                event = deepcopy(event)

                event["story_id"] = new_story_id

                events_to_copy.append(event)


if events_to_copy:
    target["web_story_events"].insert_many(
        events_to_copy
    )


print(
    "Web Story Events copied:",
    len(events_to_copy)
)


# ============================================================
# 8. WRITER APPLICATION
# ============================================================

print("\n" + "=" * 70)
print("8. WRITER APPLICATION")
print("=" * 70)

applications2 = get_documents(
    db2,
    "writer_applications"
)

applications1 = get_documents(
    db1,
    "writer_applications"
)

applications = applications2 + applications1

if applications:

    # Keep exactly ONE application.
    application = deepcopy(
        applications[0]
    )

    application["_id"] = new_id()

    # Remap obvious applicant reference.
    for field in [
        "user_id",
        "applicant_id",
        "writer_id",
    ]:

        if field in application:

            application[field] = str(
                new_writer_id
            )

    target[
        "writer_applications"
    ].insert_one(application)

    print("Writer applications kept: 1")

    print(
        "Application fields:",
        ", ".join(
            sorted(application.keys())
        )
    )

else:

    print("No writer applications found.")


# ============================================================
# 9. NOTIFICATIONS
# ============================================================

print("\n" + "=" * 70)
print("9. NOTIFICATIONS")
print("=" * 70)

notifications = []

for source_db in [db1, db2]:

    for notification in get_documents(
        source_db,
        "notifications"
    ):

        notification = deepcopy(
            notification
        )

        user_id = str(
            notification.get(
                "user_id",
                ""
            )
        )

        if user_id in old_super_admin_ids:
            notification["user_id"] = str(
                new_super_admin_id
            )

        elif user_id in old_writer_ids:
            notification["user_id"] = str(
                new_writer_id
            )

        elif user_id == "super_admin":
            notification["user_id"] = str(
                new_super_admin_id
            )

        notifications.append(
            notification
        )


notification_ids = set()

for notification in notifications:

    notification_id = str(
        notification["_id"]
    )

    if notification_id in notification_ids:
        notification["_id"] = new_id()

    notification_ids.add(
        str(notification["_id"])
    )

    target[
        "notifications"
    ].insert_one(notification)


print(
    "Notifications copied:",
    len(notifications)
)


# ============================================================
# 10. ACTIVITY LOGS
# ============================================================

print("\n" + "=" * 70)
print("10. ACTIVITY LOGS")
print("=" * 70)

logs = []

for source_db in [db1, db2]:

    for log in get_documents(
        source_db,
        "activity_logs"
    ):

        log = deepcopy(log)

        for field in [
            "user_id",
            "actor_id",
            "author_id",
            "created_by",
            "updated_by",
            "reviewed_by",
            "approved_by",
        ]:

            if field not in log:
                continue

            value = str(log[field])

            if value in old_super_admin_ids:

                log[field] = str(
                    new_super_admin_id
                )

            elif value in old_writer_ids:

                log[field] = str(
                    new_writer_id
                )

        logs.append(log)


log_ids = set()

for log in logs:

    log_id = str(log["_id"])

    if log_id in log_ids:
        log["_id"] = new_id()

    log_ids.add(str(log["_id"]))

    target[
        "activity_logs"
    ].insert_one(log)


print(
    "Activity logs copied:",
    len(logs)
)


# ============================================================
# 11. CONTENT / CONTENTS
# ============================================================

print("\n" + "=" * 70)
print("11. CONTENT / CONTENTS")
print("=" * 70)

for collection_name in [
    "content",
    "contents",
]:

    documents = get_documents(
        db1,
        collection_name
    )

    if documents:

        for document in documents:
            document = deepcopy(document)

            if target[
                collection_name
            ].find_one(
                {"_id": document["_id"]}
            ):
                document["_id"] = new_id()

            target[
                collection_name
            ].insert_one(document)

    print(
        collection_name,
        ":",
        len(documents)
    )


# ============================================================
# 12. SETTINGS
# ============================================================

print("\n" + "=" * 70)
print("12. SETTINGS")
print("=" * 70)

settings1 = get_documents(
    db1,
    "settings"
)

settings2 = get_documents(
    db2,
    "settings"
)

settings_documents = settings1 + settings2

if settings_documents:

    # Prefer cms_db settings because that copy
    # was updated most recently in the supplied data.
    settings_doc = deepcopy(
        settings1[0]
        if settings1
        else settings_documents[0]
    )

    settings_doc["_id"] = new_id()

    # Remap featured categories.
    featured_categories = settings_doc.get(
        "featured_category_ids",
        []
    )

    settings_doc[
        "featured_category_ids"
    ] = [
        category_id_map.get(
            str(category_id),
            str(category_id)
        )
        for category_id in featured_categories
    ]

    # Check hero article.
    hero_id = settings_doc.get(
        "hero_article_id"
    )

    hero_exists = target[
        "articles"
    ].find_one(
        {
            "_id": ObjectId(hero_id)
        }
        if hero_id
        and ObjectId.is_valid(str(hero_id))
        else {
            "_id": hero_id
        }
    )

    if hero_exists is None:

        # Pick a featured article.
        featured_article = target[
            "articles"
        ].find_one(
            {
                "is_featured": True,
                "status": "published"
            }
        )

        if featured_article is None:

            featured_article = target[
                "articles"
            ].find_one(
                {
                    "status": "published"
                }
            )

        if featured_article:

            settings_doc[
                "hero_article_id"
            ] = str(
                featured_article["_id"]
            )

    settings_doc[
        "updated_at"
    ] = datetime.utcnow()

    target[
        "settings"
    ].insert_one(settings_doc)

    print("Settings copied: 1")

else:

    print("No settings found.")


# ============================================================
# 13. CLEAN SESSIONS
# ============================================================

print("\n" + "=" * 70)
print("13. SESSIONS")
print("=" * 70)

# Do NOT copy old sessions.
# Old sessions belong to deleted users.

print(
    "Sessions copied: 0"
)
print(
    "Users will log in again."
)


# ============================================================
# 14. CREATE USEFUL INDEXES
# ============================================================

print("\n" + "=" * 70)
print("14. INDEXES")
print("=" * 70)

try:
    target["users"].create_index(
        "username",
        unique=True
    )

    target["users"].create_index(
        "email",
        unique=True
    )

    target["categories"].create_index(
        "slug",
        unique=True
    )

    target["tags"].create_index(
        "slug",
        unique=True
    )

    print("Indexes created.")

except Exception as error:
    print("Index warning:", error)


# ============================================================
# 15. FINAL VERIFICATION
# ============================================================

print("\n" + "=" * 70)
print("FINAL DATABASE VERIFICATION")
print("=" * 70)

collections = sorted(
    target.list_collection_names()
)

for collection in collections:

    count = target[
        collection
    ].count_documents({})

    print(
        f"{collection:25} {count}"
    )


print("\n" + "=" * 70)
print("MERGE FINISHED SUCCESSFULLY")
print("=" * 70)

print("\nTarget:")
print("  dorecord_merged")

print("\nOriginal databases were NOT changed:")
print("  cms_db")
print("  dorecord_cms_db")

print("\nIMPORTANT:")
print("This merge used LOCAL MongoDB only.")
print("Atlas was NOT modified.")

client.close()