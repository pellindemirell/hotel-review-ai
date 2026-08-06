"""Test the full ABSA platform flow (no server needed)"""
import sys, json, uuid, os
sys.path.insert(0, ".")

from app.absa_platform.database import (
    init_dbs, seed_users, import_reviews_from_json,
    assign_reviews_batch, get_source_db, get_gold_db,
    push_to_gold, export_gold_for_training, get_gold_stats
)

# Reset
for f in ["source.db", "gold.db"]:
    p = os.path.join("app/absa_platform", f)
    if os.path.exists(p):
        os.remove(p)

init_dbs()
seed_users()

jp = r"D:\KodYazılımStaj1\datasets\gold\annotated\annotated_batch_002.json"
import_reviews_from_json(jp)
assign_reviews_batch(5000)

print("\n--- Source DB: users and assignments ---")
with get_source_db() as db:
    for u in db.execute("SELECT username, display_name, role FROM users"):
        print(f"  {u['username']:15s} {u['display_name']:15s} {u['role']}")
    assign_count = db.execute("SELECT status, COUNT(*) as cnt FROM review_assignments GROUP BY status").fetchall()
    for r in assign_count:
        print(f"  Assignments: {r['status']} = {r['cnt']}")

print("\n--- Simulate: Arda1 reviews and corrects ---")
with get_source_db() as db:
    user = db.execute("SELECT id, username FROM users WHERE username='arda1'").fetchone()
    review = db.execute("""
        SELECT r.id, r.review_text FROM review_assignments ra
        JOIN reviews r ON r.id = ra.review_id
        WHERE ra.user_id=%s AND ra.status='pending' LIMIT 1
    """, (user['id'],)).fetchone()

    absa = db.execute("SELECT aspects_json, departments_json FROM absa_auto WHERE review_id=%s", (review['id'],)).fetchone()

print(f"  Review: {review['id']}")
print(f"  Text: {review['review_text'][:80]}...")
aspects = json.loads(absa['aspects_json'])
depts = json.loads(absa['departments_json'])
print(f"  Auto aspects ({len(aspects)}): {[a['aspect'] for a in aspects]}")
print(f"  Auto depts ({len(depts)}): {[d['department'] for d in depts]}")

# Simulate correction: approve first aspect, correct second
for a in aspects:
    a['approved'] = True  # approve all
aspects[0]['approved'] = True
for d in depts:
    d['approved'] = True

push_to_gold(
    review_id=review['id'],
    aspects=aspects,
    departments=depts,
    reviewer_username="arda1",
    quality_score=100.0,
)

print("\n--- Gold DB stats ---")
stats = get_gold_stats()
print(f"  Records: {stats['total']}")
print(f"  Languages: {stats['languages']}")

print("\n--- Training export ---")
data = export_gold_for_training()
print(f"  {len(data)} records ready for model training")
if data:
    d = data[0]
    print(f"  Sample: {d['review_text'][:60]}...")
    print(f"  Aspects: {d['aspects_json'][:80]}...")
    print(f"  Depts: {d['departments_json'][:80]}...")
    print(f"  Reviewer: {d['reviewer_username']}")

print("\n✅ FULL FLOW TEST PASSED!")
