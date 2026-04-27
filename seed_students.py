# seed_students.py
# Run once: python seed_students.py

import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import init_db, init_students_table, get_db

def seed():
    init_db()
    init_students_table()
    print("Seeding student accounts...")

    STUDENTS = [
        # username     password    full_name               prog_id  semester
        ("bca_s1",    "pass123",  "Rahul Sharma",          2,       1),
        ("bca_s2",    "pass123",  "Priya Das",             2,       2),
        ("mas_s1",    "pass123",  "Anjali Bora",           1,       1),
        ("mas_s2",    "pass123",  "Dipankar Gogoi",        1,       2),
        ("bcom_s1",   "pass123",  "Riya Kalita",           3,       1),
        ("meg_s1",    "pass123",  "Subham Hazarika",       4,       1),
    ]

    conn = get_db()

    # Admin uses NULL programme_id — disable FK check just for this insert
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute("""
        INSERT OR IGNORE INTO students (username, password, full_name, programme_id, semester)
        VALUES (?, ?, ?, NULL, NULL)
    """, ("admin", "admin123", "Admin User"))
    conn.execute("PRAGMA foreign_keys = ON")
    conn.commit()
    print("  ✓ admin (no programme — redirects to /library on login)")

    # Regular students
    for username, password, full_name, prog_id, semester in STUDENTS:
        try:
            conn.execute("""
                INSERT OR IGNORE INTO students (username, password, full_name, programme_id, semester)
                VALUES (?, ?, ?, ?, ?)
            """, (username, password, full_name, prog_id, semester))
            conn.commit()
            print(f"  ✓ {username} → programme_id={prog_id}, sem={semester}")
        except Exception as e:
            print(f"  ⚠ {username} skipped: {e}")

    conn.close()
    print("\n✅ Done! Login credentials:")
    print("   bca_s1 / pass123  →  BCA Semester 1")
    print("   bca_s2 / pass123  →  BCA Semester 2")
    print("   mas_s1 / pass123  →  MAS Semester 1")
    print("   mas_s2 / pass123  →  MAS Semester 2")
    print("   bcom_s1 / pass123 →  BCOM Semester 1")
    print("   meg_s1 / pass123  →  MEG Semester 1")
    print("   admin  / admin123 →  Full access")

if __name__ == "__main__":
    seed()
