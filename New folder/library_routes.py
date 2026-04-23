# library_routes.py
# All Flask routes for the course library feature.
# Register in app.py with:
#   from library_routes import library_bp
#   app.register_blueprint(library_bp)

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
# PAGE
# ─────────────────────────────────────────────────────────────

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
