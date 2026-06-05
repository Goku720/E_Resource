# seed.py
# Only seeds the admin account.
# All programmes and papers are populated automatically via the KKHSOU API
# when real students log in for the first time.
# Usage: python seed.py

from database import init_db, get_db


def seed():
    init_db()
    conn = get_db()

    with conn.cursor() as cur:
        cur.execute("""
            INSERT IGNORE INTO students (username, password, full_name, programme_id, semester)
            VALUES ('admin', 'admin123', 'Admin User', NULL, NULL)
        """)
        conn.commit()
        print("  ✓ admin account seeded (admin / admin123)")

    conn.close()
    print("\n✅ Seeding complete.")
    print("   Real students log in with their KKHSOU mobile number + password.")
    print("   Programmes and papers are auto-populated on first student login.")


if __name__ == "__main__":
    seed()
