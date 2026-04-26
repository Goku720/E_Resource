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
 
library_bp = Blueprint("library", __name__)
 
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
# PAGES
# ─────────────────────────────────────────────────────────────
 
@library_bp.route("/library")
def library():
    if "user" not in session:
        return redirect(url_for("login"))
    return render_template("library.html")
 
 
@library_bp.route("/admin/library")
def admin_library():
    return render_template("admin_library.html")
 
 
# ─────────────────────────────────────────────────────────────
# JSON API — read
# ─────────────────────────────────────────────────────────────
 
@library_bp.route("/api/programmes")
def api_programmes():
    # 🔁 SWAP LATER: requests.get(f"{EXTERNAL_API}/api/programmes").json()
    return jsonify(fetch_all_programmes())
 
 
@library_bp.route("/api/semesters/<int:programme_id>")
def api_semesters(programme_id):
    # 🔁 SWAP LATER: requests.get(f"{EXTERNAL_API}/api/semesters/{programme_id}").json()
    return jsonify(fetch_semesters(programme_id))
 
 
@library_bp.route("/api/papers/<int:programme_id>/<int:semester>")
def api_papers(programme_id, semester):
    programme = fetch_programme_by_id(programme_id)
    if not programme:
        return jsonify({"error": "Programme not found"}), 404
 
    papers = fetch_papers_with_pdfs(programme_id, semester)
 
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
    for t in grouped:
        if t not in TYPE_ORDER:
            ordered_groups.append({
                "type": t,
                "label": TYPE_LABELS.get(t, t),
                "papers": grouped[t]
            })
 
    total_papers = sum(len(g["papers"]) for g in ordered_groups)
    total_pdfs   = sum(len(p["pdfs"]) for g in ordered_groups for p in g["papers"])
    ready_pdfs   = sum(
        1 for g in ordered_groups
        for p in g["papers"]
        for pdf in p["pdfs"]
        if pdf["status"] == "ready"
    )
 
    return jsonify({
        "programme": programme,
        "semester":  semester,
        "groups":    ordered_groups,
        "stats": {
            "total_papers": total_papers,
            "total_pdfs":   total_pdfs,
            "ready_pdfs":   ready_pdfs,
        }
    })
 
 
@library_bp.route("/api/pdf_status/<pdf_name>")
def api_pdf_status(pdf_name):
    pdf = fetch_pdf_by_name(pdf_name)
    if not pdf:
        return jsonify({"status": "not_found"})
    return jsonify({"status": pdf["status"], "title": pdf["title"]})
 
 
# ─────────────────────────────────────────────────────────────
# ADMIN — upload
# ─────────────────────────────────────────────────────────────
 
@library_bp.route("/admin/library/upload", methods=["POST"])
def admin_library_upload():
    file     = request.files.get("pdf")
    pdf_name = request.form.get("pdf_name", "").strip()
 
    if not file or file.filename == "":
        return jsonify({"error": "No file uploaded"}), 400
    if not file.filename.lower().endswith(".pdf"):
        return jsonify({"error": "Only PDF files are allowed"}), 400
    if not pdf_name:
        return jsonify({"error": "pdf_name is required"}), 400
 
    pdf_row = fetch_pdf_by_name(pdf_name)
    if not pdf_row:
        return jsonify({"error": f"No PDF slot found for '{pdf_name}'"}), 404
 
    file_path = pdf_row["file_path"]
    folder    = os.path.dirname(file_path)
    os.makedirs(folder, exist_ok=True)
    file.save(file_path)
 
    update_pdf_status(pdf_name, "processing")
    process_book_task.delay(pdf_name, file_path)
 
    return jsonify({
        "ok":       True,
        "pdf_name": pdf_name,
        "status":   "processing",
        "message":  "Uploaded successfully. Processing started in background."
    })
 
 
# ─────────────────────────────────────────────────────────────
# ADMIN — add new block to a paper
# ─────────────────────────────────────────────────────────────
 
@library_bp.route("/api/admin/add_block", methods=["POST"])
def add_block():
    data     = request.get_json()
    paper_id = data.get("paper_id")
    title    = data.get("title", "").strip()
 
    if not paper_id or not title:
        return jsonify({"error": "paper_id and title are required"}), 400
 
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
 
    # Auto-number the new block
    existing = conn.execute(
        "SELECT COUNT(*) as cnt FROM pdfs WHERE paper_id = ?", (paper_id,)
    ).fetchone()["cnt"]
 
    block_num  = existing + 1
    safe_title = title.replace(" ", "_").replace("/", "-")[:40]
    pdf_name   = f"{paper['code']}_S{paper['semester']}_P{paper_id}_Block{block_num}_{safe_title}"
 
    folder = os.path.join(
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
        "ok":        True,
        "id":        new_id,
        "pdf_name":  pdf_name,
        "title":     title,
        "status":    "pending",
        "file_path": file_path
    })
 
 
# ─────────────────────────────────────────────────────────────
# ADMIN — remove a block (PDF slot)
# ─────────────────────────────────────────────────────────────
 
@library_bp.route("/api/admin/remove_block/<int:pdf_id>", methods=["DELETE"])
def remove_block(pdf_id):
    conn = get_db()
    pdf  = conn.execute("SELECT * FROM pdfs WHERE id = ?", (pdf_id,)).fetchone()
 
    if not pdf:
        conn.close()
        return jsonify({"error": "Block not found"}), 404
 
    pdf = dict(pdf)
    file_path = pdf["file_path"]
 
    def _mirror(base, fp, up="uploads"):
        try:
            rel = os.path.relpath(fp, up)
            return os.path.join(base, os.path.splitext(rel)[0] + ".json")
        except ValueError:
            return None
 
    # Delete PDF file
    if file_path and os.path.exists(file_path):
        os.remove(file_path)
 
    # Delete summaries, page_texts, status — try mirrored path first, then flat
    for folder in ["summaries", "page_texts", "status"]:
        paths_to_try = []
        if file_path:
            m = _mirror(folder, file_path)
            if m:
                paths_to_try.append(m)
        paths_to_try.append(os.path.join(folder, f"{pdf['pdf_name']}.json"))
 
        for p in paths_to_try:
            if p and os.path.exists(p):
                os.remove(p)
                break   # only delete once
 
    conn.execute("DELETE FROM pdfs WHERE id = ?", (pdf_id,))
    conn.commit()
    conn.close()
 
    return jsonify({
        "ok":      True,
        "id":      pdf_id,
        "message": f"Block '{pdf['title']}' removed."
    })
 
 
# ─────────────────────────────────────────────────────────────
# ADMIN — mark ready manually
# ─────────────────────────────────────────────────────────────
 
@library_bp.route("/api/admin/mark_ready/<pdf_name>", methods=["POST"])
def mark_ready(pdf_name):
    update_pdf_status(pdf_name, "ready")
    return jsonify({"ok": True, "pdf_name": pdf_name, "status": "ready"})