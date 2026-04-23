# ════════════════════════════════════════════════════════════
# CHANGES NEEDED IN YOUR EXISTING app.py  (only 2 additions)
# ════════════════════════════════════════════════════════════

# 1. Add this import near the top (after your existing imports):
from library_routes import library_bp

# 2. Add this line right after:  app = Flask(__name__)
app.register_blueprint(library_bp)


# ════════════════════════════════════════════════════════════
# ALSO: update your existing /admin/upload route
# so that after Celery processes a PDF it marks it ready in DB
# ════════════════════════════════════════════════════════════
#
# In tasks.py, at the very end of process_book_task(),
# after:  update_status(pdf_name, "ready", 100, "Book processing completed successfully.")
# Add:
#
#   from database import update_pdf_status
#   update_pdf_status(pdf_name, "ready")
#
# That's it — the library page will automatically show
# "Ready to read" for any PDF that finishes processing.


# ════════════════════════════════════════════════════════════
# FULL FILE STRUCTURE  (new files to add)
# ════════════════════════════════════════════════════════════
#
# project/
# ├── app.py                  ← existing (add 2 lines above)
# ├── tasks.py                ← existing (add 2 lines above)
# ├── database.py             ← NEW
# ├── seed.py                 ← NEW  (run once: python seed.py)
# ├── library_routes.py       ← NEW
# ├── templates/
# │   ├── library.html        ← NEW  (copy here)
# │   └── ... existing templates
# └── library.db              ← auto-created by seed.py


# ════════════════════════════════════════════════════════════
# SETUP STEPS (run in order)
# ════════════════════════════════════════════════════════════
#
# 1. Copy all new files into your project folder
# 2. python seed.py               ← creates library.db + fills dummy data
# 3. python app.py                ← start Flask as usual
# 4. Visit http://localhost:5000/library
#
# When real API arrives:
#   - Open seed.py
#   - Replace PROGRAMMES / PAPERS / PDFS lists with API calls
#   - Re-run: python seed.py
#   - Nothing else changes
