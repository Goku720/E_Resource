# library_routes.py
# All Flask routes for the course library feature.
# Register in app.py with:
#   from library_routes import library_bp
#   app.register_blueprint(library_bp)

# library_routes.py

import os
from flask import Blueprint, render_template, jsonify, session, redirect, url_for, request
from database import (
    fetch_all_programmes,
    fetch_semesters,
    fetch_papers_with_pdfs,
    fetch_programme_by_id,
    fetch_pdf_by_name,
    update_pdf_status,
    get_db
)
from tasks import process_book_task

TYPE_LABELS = {
    "DSC": "Discipline Specific Core",
    "DSE": "Discipline Specific Elective",
    "AEC": "Ability Enhancement Compulsory",
    "VAC": "Value Added Course",
    "GE":  "Generic Elective",
    "SEC": "Skill Enhancement Course",
}
TYPE_ORDER = ["DSC", "DSE", "AEC", "VAC", "GE", "SEC"]


# ─────────────────────────────────────────────────────────────
# PAGE
# ─────────────────────────────────────────────────────────────
library_bp = Blueprint("library", __name__)

@library_bp.route("/library")
def library():
    if "user" not in session:
        return redirect(url_for("login"))
    return render_template("library.html")


# ─────────────────────────────────────────────────────────────
# JSON API  (called by the frontend JS)
# ─────────────────────────────────────────────────────────────

@library_bp.route("/api/programmes")
def api_programmes():
    """
    Returns all programmes.
    🔁 SWAP LATER: replace fetch_all_programmes() with real API call
        import requests
        data = requests.get(f"{EXTERNAL_API}/api/programmes").json()
        return jsonify(data)
    """
    return jsonify(fetch_all_programmes())


@library_bp.route("/api/semesters/<int:programme_id>")
def api_semesters(programme_id):
    """
    Returns available semester numbers for a programme.
    🔁 SWAP LATER: replace fetch_semesters() with real API call
    """
    return jsonify(fetch_semesters(programme_id))


@library_bp.route("/api/papers/<int:programme_id>/<int:semester>")
def api_papers(programme_id, semester):
    """
    Returns papers + PDFs for a programme/semester, grouped by paper type.
    🔁 SWAP LATER: replace fetch_papers_with_pdfs() with real API call,
       then call download_and_save() for each PDF, then insert into DB.
    """
    programme = fetch_programme_by_id(programme_id)
    if not programme:
        return jsonify({"error": "Programme not found"}), 404

    papers = fetch_papers_with_pdfs(programme_id, semester)

    # Group by paper type in a predictable order
    grouped = {}
    for paper in papers:
        ptype = paper["paper_type"]
        if ptype not in grouped:
            grouped[ptype] = []
        grouped[ptype].append(paper)

    ordered_groups = []
    for t in TYPE_ORDER:
        if t in grouped:
            ordered_groups.append({
                "type": t,
                "label": TYPE_LABELS.get(t, t),
                "papers": grouped[t]
            })
    for t in grouped:   # any types not in our known order
        if t not in TYPE_ORDER:
            ordered_groups.append({
                "type": t,
                "label": TYPE_LABELS.get(t, t),
                "papers": grouped[t]
            })

    # Stats
    total_papers = sum(len(g["papers"]) for g in ordered_groups)
    total_pdfs   = sum(len(p["pdfs"]) for g in ordered_groups for p in g["papers"])
    ready_pdfs   = sum(
        1 for g in ordered_groups
        for p in g["papers"]
        for pdf in p["pdfs"]
        if pdf["status"] == "ready"
    )

    return jsonify({
        "programme":    programme,
        "semester":     semester,
        "groups":       ordered_groups,
        "stats": {
            "total_papers": total_papers,
            "total_pdfs":   total_pdfs,
            "ready_pdfs":   ready_pdfs,
        }
    })


@library_bp.route("/api/pdf_status/<pdf_name>")
def api_pdf_status(pdf_name):
    """Check processing status of a single PDF."""
    pdf = fetch_pdf_by_name(pdf_name)
    if not pdf:
        return jsonify({"status": "not_found"})
    return jsonify({"status": pdf["status"], "title": pdf["title"]})



@library_bp.route("/api/admin/add_block", methods=["POST"])
def add_block():
    data     = request.get_json()
    paper_id = data.get("paper_id")
    title    = data.get("title", "").strip()

    if not paper_id or not title:
        return jsonify({"error": "paper_id and title are required"}), 400

    # Build pdf_name — need paper info to construct the path
    conn  = get_db()
    paper = conn.execute("""
        SELECT p.*, pr.code, pr.name as prog_name
        FROM papers p
        JOIN programmes pr ON pr.id = p.programme_id
        WHERE p.id = ?
    """, (paper_id,)).fetchone()

    if not paper:
        conn.close()
        return jsonify({"error": "Paper not found"}), 404

    # Count existing blocks for this paper to auto-number
    existing = conn.execute(
        "SELECT COUNT(*) as cnt FROM pdfs WHERE paper_id = ?", (paper_id,)
    ).fetchone()["cnt"]

    block_num = existing + 1
    safe_title = title.replace(" ", "_").replace("/", "-")[:40]
    pdf_name  = f"{paper['code']}_S{paper['semester']}_P{paper_id}_Block{block_num}_{safe_title}"

    folder    = os.path.join(
        "uploads",
        paper["code"],
        f"Semester_{paper['semester']}",
        paper["paper_name"].replace(" ", "_").replace("/", "-")[:50]
    )
    file_path = os.path.join(folder, f"{pdf_name}.pdf")

    conn.execute("""
        INSERT INTO pdfs (paper_id, title, pdf_name, file_path, status)
        VALUES (?, ?, ?, ?, 'pending')
    """, (paper_id, title, pdf_name, file_path))
    conn.commit()

    new_id = conn.execute("SELECT last_insert_rowid() as id").fetchone()["id"]
    conn.close()

    return jsonify({
        "ok":       True,
        "id":       new_id,
        "pdf_name": pdf_name,
        "title":    title,
        "status":   "pending",
        "file_path": file_path
    })

# ─────────────────────────────────────────────────────────────
# ADMIN — mark a PDF as ready after uploading it manually
# ─────────────────────────────────────────────────────────────

@library_bp.route("/api/admin/mark_ready/<pdf_name>", methods=["POST"])
def mark_ready(pdf_name):
    """
    After an admin uploads a real PDF, call this to mark it ready.
    This is called automatically by the existing /admin/upload route
    once Celery finishes processing.
    """
    update_pdf_status(pdf_name, "ready")
    return jsonify({"ok": True, "pdf_name": pdf_name, "status": "ready"})














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


