# ─────────────────────────────────────────────────────────────
# ADD THIS TO library_routes.py
# (paste below the existing routes)
# ─────────────────────────────────────────────────────────────

import os
from flask import request, jsonify, render_template
from tasks import process_book_task          # your existing Celery task
from database import fetch_pdf_by_name, update_pdf_status, get_db


@library_bp.route("/admin/library")
def admin_library():
    """Admin page for uploading PDFs to specific paper slots."""
    return render_template("admin_library.html")


@library_bp.route("/admin/library/upload", methods=["POST"])
def admin_library_upload():
    """
    Upload a PDF into a specific slot in the library.
    Expects:  pdf       (file)
              pdf_name  (the unique key, e.g. "MAS_S1_P1_Block1")
              pdf_id    (the DB row id)
    """
    file     = request.files.get("pdf")
    pdf_name = request.form.get("pdf_name", "").strip()
    pdf_id   = request.form.get("pdf_id", "").strip()

    # ── Validate ──────────────────────────────────────────
    if not file or file.filename == "":
        return jsonify({"error": "No file uploaded"}), 400

    if not file.filename.lower().endswith(".pdf"):
        return jsonify({"error": "Only PDF files are allowed"}), 400

    if not pdf_name:
        return jsonify({"error": "pdf_name is required"}), 400

    # ── Look up the slot in the DB ────────────────────────
    pdf_row = fetch_pdf_by_name(pdf_name)
    if not pdf_row:
        return jsonify({"error": f"No PDF slot found for '{pdf_name}'"}), 404

    # ── Save to the correct folder ────────────────────────
    file_path = pdf_row["file_path"]          # path was pre-built by seed.py
    folder    = os.path.dirname(file_path)

    os.makedirs(folder, exist_ok=True)        # create folder if not exists
    file.save(file_path)                      # save PDF to disk

    # ── Mark as processing in DB ──────────────────────────
    update_pdf_status(pdf_name, "processing")

    # ── Trigger your existing Celery pipeline ─────────────
    # process_book_task expects (pdf_name, pdf_path) exactly
    # like your existing /admin/upload route does
    process_book_task.delay(pdf_name, file_path)

    return jsonify({
        "ok":       True,
        "pdf_name": pdf_name,
        "status":   "processing",
        "message":  "Uploaded successfully. Processing started in background."
    })


# ─────────────────────────────────────────────────────────────
# ALSO: update tasks.py so it marks the PDF ready in DB
# when Celery finishes processing.
#
# At the very end of process_book_task(), after:
#   update_status(pdf_name, "ready", 100, "Book processing completed.")
#
# Add these two lines:
#   from database import update_pdf_status
#   update_pdf_status(pdf_name, "ready")
#
# That's it — the admin page will auto-update to "Ready" via polling.
# ─────────────────────────────────────────────────────────────
