import sys
sys.path.insert(0, ".")
from app.absa_platform.database import init_dbs, seed_users, import_reviews_from_json, assign_reviews_batch, get_source_db
import time
t0 = time.time()
init_dbs()
seed_users()
jp = r"D:\KodYazılımStaj1\datasets\gold\annotated\annotated_batch_002.json"
import_reviews_from_json(jp)
assign_reviews_batch(5000)
print(f"Done in {time.time()-t0:.1f}s")

with get_source_db() as db:
    users = db.execute("SELECT username, display_name, role FROM users").fetchall()
    print("\nUsers:")
    for u in users:
        print(f"  {u['username']:15s} {u['display_name']:15s} {u['role']}")
