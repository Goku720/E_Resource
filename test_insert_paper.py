# test_insert_paper.py
# Inserts ONE dummy paper directly, without calling the real KKHSOU API.
# Use this to test the paper -> upload pipeline while USE_FAKE_LOGIN=True.
# Usage: docker compose exec web python test_insert_paper.py

from paper_sync import store_papers
from database import get_db

PROGRAMME_ID = 2      # bca_s1's programme_id, from seed_students.py
SEMESTER     = 1
PROG_CODE    = "BCA"  # used by store_papers() to decide bachelor/master logic

dummy_paper = {
    "paper_name": "Test Paper - Data Structures",
    "group_code": "MAJOR",
    "group_type": "core",
}

print("Inserting dummy paper...")
count = store_papers(PROGRAMME_ID, SEMESTER, [dummy_paper], PROG_CODE)
print(f"Inserted {count} new paper(s).")

print("\nVerifying in DB...")
conn = get_db()
with conn.cursor() as cur:
    cur.execute(
        "SELECT id, paper_type, paper_name FROM papers WHERE programme_id=%s AND semester=%s ORDER BY id",
        (PROGRAMME_ID, SEMESTER)
    )
    rows = cur.fetchall()
conn.close()

print(f"Found {len(rows)} paper(s) in DB:")
for r in rows:
    print(f"  id={r['id']} [{r['paper_type']}] {r['paper_name']}")