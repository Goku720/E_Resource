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
DB_PATH          = os.environ.get("DB_PATH",           "library.db")
SECRET_KEY       = os.environ.get("SECRET_KEY",        "dev-secret-key")

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
