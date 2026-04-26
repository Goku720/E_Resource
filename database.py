# database.py
# SQLite database setup for the course library.
# Run once: python database.py
# ──────────────────────────────────────────────

import sqlite3
import os

DB_PATH = "library.db"

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row          # access columns by name
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    conn = get_db()
    conn.executescript("""

        -- Programmes: MAS, BCA, BCOM etc.
        CREATE TABLE IF NOT EXISTS programmes (
            id      INTEGER PRIMARY KEY,
            code    TEXT UNIQUE NOT NULL,   -- "MAS", "BCA"
            name    TEXT NOT NULL           -- "Master of Arts in Assamese"
        );

        -- Papers: one row per paper per semester
        CREATE TABLE IF NOT EXISTS papers (
            id            INTEGER PRIMARY KEY,
            programme_id  INTEGER NOT NULL,
            semester      INTEGER NOT NULL,
            paper_type    TEXT NOT NULL,    -- DSC / DSE / AEC / VAC / GE / SEC
            paper_name    TEXT NOT NULL,
            FOREIGN KEY (programme_id) REFERENCES programmes(id)
        );

        -- PDFs: MULTIPLE per paper (Block 1, Block 2 …)
        CREATE TABLE IF NOT EXISTS pdfs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            paper_id    INTEGER NOT NULL,
            title       TEXT NOT NULL,      -- "Block 1", "Unit 2" …
            pdf_name    TEXT UNIQUE,        -- unique key used by flipbook/summary routes
            file_path   TEXT,              -- path on disk, e.g. uploads/MAS/Sem1/.../Block1.pdf
            status      TEXT DEFAULT 'pending',  -- pending / processing / ready / failed
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (paper_id) REFERENCES papers(id)
        );

    """)
    conn.commit()
    conn.close()
    print("✅ Database initialised → library.db")

# ── Helper queries used by the Flask routes ──────────────────

def fetch_all_programmes():
    conn = get_db()
    rows = conn.execute("SELECT * FROM programmes ORDER BY code").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def fetch_semesters(programme_id):
    conn = get_db()
    rows = conn.execute(
        "SELECT DISTINCT semester FROM papers WHERE programme_id=? ORDER BY semester",
        (programme_id,)
    ).fetchall()
    conn.close()
    return [r["semester"] for r in rows]

def fetch_papers_with_pdfs(programme_id, semester):
    conn = get_db()

    papers = conn.execute(
        """SELECT * FROM papers
           WHERE programme_id=? AND semester=?
           ORDER BY paper_type, id""",
        (programme_id, semester)
    ).fetchall()

    result = []
    for paper in papers:
        pdfs = conn.execute(
            "SELECT * FROM pdfs WHERE paper_id=? ORDER BY id",
            (paper["id"],)
        ).fetchall()
        d = dict(paper)
        d["pdfs"] = [dict(p) for p in pdfs]
        result.append(d)

    conn.close()
    return result

def fetch_programme_by_id(programme_id):
    conn = get_db()
    row = conn.execute("SELECT * FROM programmes WHERE id=?", (programme_id,)).fetchone()
    conn.close()
    return dict(row) if row else None

def fetch_pdf_by_name(pdf_name):
    conn = get_db()
    row = conn.execute("SELECT * FROM pdfs WHERE pdf_name=?", (pdf_name,)).fetchone()
    conn.close()
    return dict(row) if row else None

def update_pdf_status(pdf_name, status):
    conn = get_db()
    conn.execute("UPDATE pdfs SET status=? WHERE pdf_name=?", (status, pdf_name))
    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
