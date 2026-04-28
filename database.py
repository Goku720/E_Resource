# database.py
# MySQL database setup for the course library.
# Run once: python database.py
# ──────────────────────────────────────────────

import pymysql
import pymysql.cursors
from config import MYSQL_HOST, MYSQL_PORT, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DB


def get_db():
    """
    Returns a new MySQL connection with DictCursor so columns
    are accessible by name (mirrors sqlite3.Row behaviour).
    """
    conn = pymysql.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_DB,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )
    return conn


def init_db():
    conn = get_db()
    with conn.cursor() as cur:
        # Programmes: MAS, BCA, BCOM etc.
        cur.execute("""
            CREATE TABLE IF NOT EXISTS programmes (
                id   INT          PRIMARY KEY,
                code VARCHAR(20)  UNIQUE NOT NULL,
                name VARCHAR(255) NOT NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """)

        # Papers: one row per paper per semester
        cur.execute("""
            CREATE TABLE IF NOT EXISTS papers (
                id           INT          PRIMARY KEY,
                programme_id INT          NOT NULL,
                semester     INT          NOT NULL,
                paper_type   VARCHAR(10)  NOT NULL,
                paper_name   VARCHAR(500) NOT NULL,
                FOREIGN KEY (programme_id) REFERENCES programmes(id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """)

        # PDFs: MULTIPLE per paper (Block 1, Block 2 …)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS pdfs (
                id         INT          PRIMARY KEY AUTO_INCREMENT,
                paper_id   INT          NOT NULL,
                title      VARCHAR(500) NOT NULL,
                pdf_name   VARCHAR(500) UNIQUE,
                file_path  TEXT,
                status     VARCHAR(20)  DEFAULT 'pending',
                created_at TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (paper_id) REFERENCES papers(id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """)

    conn.commit()
    conn.close()
    print("✅ Database initialised → MySQL")


# ── Student accounts table ────────────────────────────────────

def init_students_table():
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS students (
                id           INT          PRIMARY KEY AUTO_INCREMENT,
                username     VARCHAR(100) UNIQUE NOT NULL,
                password     VARCHAR(255) NOT NULL,
                full_name    VARCHAR(255) NOT NULL,
                programme_id INT,
                semester     INT,
                created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """)
    conn.commit()
    conn.close()


# ── Helper queries used by the Flask routes ──────────────────

def fetch_all_programmes():
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM programmes ORDER BY code")
        rows = cur.fetchall()
    conn.close()
    return rows  # already list of dicts via DictCursor


def fetch_semesters(programme_id):
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT DISTINCT semester FROM papers WHERE programme_id=%s ORDER BY semester",
            (programme_id,)
        )
        rows = cur.fetchall()
    conn.close()
    return [r["semester"] for r in rows]


def fetch_papers_with_pdfs(programme_id, semester):
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute(
            """SELECT * FROM papers
               WHERE programme_id=%s AND semester=%s
               ORDER BY paper_type, id""",
            (programme_id, semester)
        )
        papers = cur.fetchall()

        result = []
        for paper in papers:
            cur.execute(
                "SELECT * FROM pdfs WHERE paper_id=%s ORDER BY id",
                (paper["id"],)
            )
            pdfs = cur.fetchall()
            paper = dict(paper)
            paper["pdfs"] = list(pdfs)
            result.append(paper)

    conn.close()
    return result


def fetch_programme_by_id(programme_id):
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM programmes WHERE id=%s", (programme_id,))
        row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def fetch_pdf_by_name(pdf_name):
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM pdfs WHERE pdf_name=%s", (pdf_name,))
        row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def update_pdf_status(pdf_name, status):
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE pdfs SET status=%s WHERE pdf_name=%s",
            (status, pdf_name)
        )
    conn.commit()
    conn.close()


def get_student(username):
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM students WHERE username=%s", (username,))
        row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def add_student(username, password, full_name, programme_id, semester):
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO students (username, password, full_name, programme_id, semester)
                   VALUES (%s, %s, %s, %s, %s)""",
                (username, password, full_name, programme_id, semester)
            )
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        return False
    finally:
        conn.close()


if __name__ == "__main__":
    init_db()
