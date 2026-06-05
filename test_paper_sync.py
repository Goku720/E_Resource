# test_paper_sync.py
# Run this directly to test paper fetching without needing to log in via browser.
# Usage: python test_paper_sync.py

import requests
from config import KKHSOU_API_BASE, KKHSOU_API_KEY
from paper_sync import fetch_selected_papers_from_api, store_papers, semester_has_papers
from database import upsert_programme_from_api, get_db

MOBILE   = "9864104792"   # ← change to a real student mobile
PASSWORD = "783517"        # ← change to their password

print(f"\n[1] Logging in as {MOBILE}...")
resp = requests.post(
    f"{KKHSOU_API_BASE}/api/v1/student/login",
    json={"mobile_no": MOBILE, "password": PASSWORD},
    headers={"Content-Type": "application/json", "X-API-KEY": KKHSOU_API_KEY},
    timeout=10,
)
body = resp.json()
if body.get("status") != "success":
    print(f"    ERROR: {body.get('message')}")
    exit(1)

data           = body["data"]
token          = data["access_token"]
enrollments    = data.get("enrollments", [])
primary        = enrollments[0] if enrollments else {}
api_prog_id    = primary.get("program_id")
prog_code      = primary.get("program_code", "")
prog_name      = primary.get("program_name", "")
semester       = primary.get("current_semester")
enrollment_no  = primary.get("enrollment_no")

print(f"    Student      : {data['student']['full_name']}")
print(f"    Program      : {prog_code} — {prog_name} (API id={api_prog_id})")
print(f"    Semester     : {semester}")
print(f"    Enrollment No: {enrollment_no}")

print(f"\n[2] Upserting programme into local DB...")
local_prog = upsert_programme_from_api(api_prog_id, prog_code, prog_name)
print(f"    Local programme id={local_prog['id']}  code={local_prog['code']}")

already = semester_has_papers(local_prog["id"], semester)
print(f"\n[3] Papers already in DB for prog_id={local_prog['id']} sem={semester}: {already}")

print(f"\n[4] Fetching selected papers from API...")
api_papers = fetch_selected_papers_from_api(enrollment_no, semester, token)
print(f"    Papers returned: {len(api_papers)}")
for p in api_papers:
    print(f"      - [{p.get('group_code')}] {p.get('paper_name')}")

if api_papers:
    print(f"\n[5] Storing papers...")
    count = store_papers(local_prog["id"], semester, api_papers)
    print(f"    Inserted {count} new papers.")
else:
    print(f"\n[5] No papers to store.")

print(f"\n[6] Verifying in DB...")
conn = get_db()
with conn.cursor() as cur:
    cur.execute(
        "SELECT id, paper_type, paper_name FROM papers WHERE programme_id=%s AND semester=%s ORDER BY id",
        (local_prog["id"], semester)
    )
    rows = cur.fetchall()
conn.close()
print(f"    Found {len(rows)} papers in DB:")
for r in rows:
    print(f"      id={r['id']} [{r['paper_type']}] {r['paper_name']}")

print("\n✅ Done.")
