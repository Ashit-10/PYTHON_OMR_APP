"""Verify the persistence changes against Mongo.

Exercises the pieces that decide whether a redeploy loses data:
per-document task/result/image writes, concurrent index writes, the legacy
image migration and the retention sweeps.

Set TEST_MONGO_URL to run against a real server, e.g.
    TEST_MONGO_URL='mongodb://localhost:27017' python3 test_persistence.py
Without it the test falls back to mongomock, which is in-process but supports
the same query and update operators the module relies on.
"""
import os
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import db

URL = os.environ.get("TEST_MONGO_URL")
if URL:
    os.environ["MONGO_URL"] = URL
    os.environ.setdefault("MONGO_DB", "omr_test")
    db.init_db()
else:
    import mongomock

    client = mongomock.MongoClient()
    db._client = client
    db.DB_NAME = "omr_test"
    print("(no TEST_MONGO_URL set; using mongomock)\n")

col = db.get_collection()
col.delete_many({})

failures = []


def check(label, cond, detail=""):
    print(f"{'PASS' if cond else 'FAIL'}  {label}{'' if cond else '  <- ' + str(detail)}")
    if not cond:
        failures.append(label)


# --- results survive independently of any image ---
db.put_result("t1", {"roll": 12, "marks": 34, "output_filename": "12_34.jpg"})
r = db.get_result("t1")
check("result round-trips", r and r["roll"] == 12 and r["marks"] == 34, r)

# --- concurrent image writes must not drop entries ---
def writer(folder, name):
    db.put_image(folder, name, {"msg_id": name, "file_id": f"fid_{name}"})

threads = [
    threading.Thread(target=writer, args=("output", f"{i}_10.jpg")) for i in range(60)
]
for t in threads:
    t.start()
for t in threads:
    t.join()

listed = db.list_images("output")
check("60 concurrent image writes all survive", len(listed) == 60, len(listed))

# --- concurrent task writes must not drop entries ---
def task_writer(i):
    db.set_task(f"task{i}", {"status": "completed", "roll": i})

threads = [threading.Thread(target=task_writer, args=(i,)) for i in range(40)]
for t in threads:
    t.start()
for t in threads:
    t.join()

check("40 concurrent task writes all survive", len(db.all_tasks()) == 40, len(db.all_tasks()))

# --- remove one image must not disturb the rest ---
db.remove_image("output", "7_10.jpg")
check(
    "removing one image leaves the others",
    len(db.list_images("output")) == 59,
    len(db.list_images("output")),
)

# --- folder-level removal ---
db.put_image("class-10_math_1", "a.jpg", {"msg_id": 1})
db.put_image("class-10_math_1", "b.jpg", {"msg_id": 2})
removed = db.remove_images_in_folder("class-10_math_1")
check("folder removal count", removed == 2, removed)
check("folder fully cleared", db.list_images("class-10_math_1") == {}, db.list_images("class-10_math_1"))
check("other folders untouched", len(db.list_images("output")) == 59, len(db.list_images("output")))

# --- legacy single-document image index migrates ---
db.set(db.IMAGES_KEY, {"output/1_5.jpg": {"msg_id": 9, "file_id": "legacy"}})
migrated = db.migrate_legacy_images()
check("legacy migration count", migrated == 1, migrated)
check("legacy entry readable", db.get_image("output", "1_5.jpg") is not None)
check("legacy blob removed", db.get(db.IMAGES_KEY) is None, db.get(db.IMAGES_KEY))
check("migration is idempotent", db.migrate_legacy_images() == 0)

# --- upload queue ---
db.queue_upload("output", "9_9.jpg", "/tmp/9_9.jpg")
q = db.get_uploads()
check("upload queued", len(q) == 1 and q[0]["filename"] == "9_9.jpg", q)
db.bump_upload_attempts("output", "9_9.jpg")
check("attempts bumped", db.get_uploads()[0]["attempts"] == 1, db.get_uploads())
db.clear_upload("output", "9_9.jpg")
check("queue cleared", db.get_uploads() == [], db.get_uploads())

# --- retention sweeps ---
# set_task/put_result stamp created_at themselves, so age the stored documents
# directly to simulate records left over from a previous deploy.
db.set_task("old", {"status": "done"})
db.set_task("t_recent", {"status": "completed"})
db.put_result("oldres", {"roll": 1, "marks": 1})
db.put_result("newres", {"roll": 2, "marks": 2})
col.update_one({"key": db.TASK_PREFIX + "old"}, {"$set": {"created_at": 1}})
col.update_one({"key": db.RESULT_PREFIX + "oldres"}, {"$set": {"created_at": 1}})

db.startup_maintenance()
check("stale task pruned", db.get_task("old") is None, db.get_task("old"))
check("stale result pruned", db.get_result("oldres") is None, db.get_result("oldres"))
check("recent result kept", db.get_result("newres") is not None, db.get_result("newres"))
check("recent task kept", db.get_task("t_recent") is not None)

col.delete_many({})
print()
if failures:
    print(f"{len(failures)} FAILED: {failures}")
    sys.exit(1)
print("all checks passed")
