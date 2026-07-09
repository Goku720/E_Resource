# config.py
# Single source of truth for all folder/path config.
# Every other file imports from here — nothing is hardcoded elsewhere.
import re
import os
from dotenv import load_dotenv

load_dotenv()   # reads .env if present; falls back to real env vars

UPLOAD_FOLDER    = os.environ.get("UPLOAD_FOLDER",    "uploads")
SUMMARY_FOLDER   = os.environ.get("SUMMARY_FOLDER",   "summaries")
PAGE_TEXT_FOLDER = os.environ.get("PAGE_TEXT_FOLDER", "page_texts")
STATUS_FOLDER    = os.environ.get("STATUS_FOLDER",    "status")
SECRET_KEY       = os.environ.get("SECRET_KEY",        "dev-secret-key")

# ── KKHSOU Student API ───────────────────────────────────────
KKHSOU_API_BASE  = os.environ.get("KKHSOU_API_BASE",  "http://192.168.31.40:8088")
KKHSOU_API_KEY   = os.environ.get("KKHSOU_API_KEY",   "password@123")

# ── MySQL connection ─────────────────────────────────────────
MYSQL_HOST     = os.environ.get("MYSQL_HOST",     "localhost")
MYSQL_PORT     = int(os.environ.get("MYSQL_PORT", 3306))
MYSQL_USER     = os.environ.get("MYSQL_USER",     "root")
MYSQL_PASSWORD = os.environ.get("MYSQL_PASSWORD", "")
MYSQL_DB       = os.environ.get("MYSQL_DB",       "library_db")

# ── Derived helpers ──────────────────────────────────────────

def build_upload_path(programme_code, semester, paper_name, pdf_name):
    # Remove all invalid filename characters (Windows-safe)
    safe_paper = re.sub(r'[\\/*?:"<>|]', "", paper_name)
    safe_paper = safe_paper.replace(" ", "_")[:50]

    folder = os.path.join(
        UPLOAD_FOLDER,
        programme_code,
        f"Semester_{semester}",
        safe_paper
    )

    return os.path.join(folder, f"{pdf_name}.pdf")

# Dev mode — set to False in production
USE_FAKE_LOGIN = True