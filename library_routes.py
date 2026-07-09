# library_routes.py

import os
from path_utils import mirror_path
from flask import Blueprint, render_template, jsonify, session, redirect, url_for, request
from database import (
    fetch_all_programmes,
    fetch_semesters,
    fetch_papers_with_pdfs,
    fetch_programme_by_id,
    fetch_minors_for_programme,
    fetch_pdf_by_name,
    update_pdf_status,
    upsert_programme_from_api,
    get_db
)
from tasks import process_book_task
from config import build_upload_path, KKHSOU_API_BASE, KKHSOU_API_KEY
from paper_sync import fetch_program_papers_from_api, store_papers, semester_has_papers, is_bachelor, KKHSOU_MINORS

library_bp = Blueprint("library", __name__)

TYPE_LABELS = {
    "DSC": "Discipline Specific Core",
    "DSE": "Discipline Specific Elective",
    "AEC": "Ability Enhancement Compulsory",
    "VAC": "Value Added Course",
    "GE":  "Generic Elective",
    "SEC": "Skill Enhancement Course",
    "FW":  "Field Work / Project",
}
TYPE_ORDER = ["DSC", "DSE", "AEC", "VAC", "GE", "SEC", "FW"]


# ─────────────────────────────────────────────────────────────
# PAGES
# ─────────────────────────────────────────────────────────────

@library_bp.route("/library")
def library():
    return render_template("library.html")


@library_bp.route("/admin/library")
def admin_library():
    return render_template("admin_library.html")


# ─────────────────────────────────────────────────────────────
# JSON API — read
# ─────────────────────────────────────────────────────────────

@library_bp.route("/api/programmes")
def api_programmes():
    return jsonify(fetch_all_programmes())


@library_bp.route("/api/semesters/<int:programme_id>")
def api_semesters(programme_id):
    return jsonify(fetch_semesters(programme_id))


@library_bp.route("/api/papers/<int:programme_id>/<int:semester>")
def api_papers(programme_id, semester):
    programme = fetch_programme_by_id(programme_id)
    if not programme:
        return jsonify({"error": "Programme not found"}), 404

    papers  = fetch_papers_with_pdfs(programme_id, semester)
    minors  = fetch_minors_for_programme(programme_id, semester)
    has_minors = len(minors) > 0

    # ── Group papers ──────────────────────────────────────────
    # For bachelor programmes with minors: group by minor first, then paper_type
    # For masters/no-minor programmes: group by paper_type only

    if has_minors:
        # Build minor → paper_type → papers structure
        minor_groups = {}
        no_minor_papers = []

        for paper in papers:
            minor = paper.get("minor")
            ptype = paper["paper_type"]
            if minor:
                if minor not in minor_groups:
                    minor_groups[minor] = {}
                if ptype not in minor_groups[minor]:
                    minor_groups[minor][ptype] = []
                minor_groups[minor][ptype].append(paper)
            else:
                no_minor_papers.append(paper)

        ordered_groups = []

        # Common papers (no minor) first
        if no_minor_papers:
            common_by_type = {}
            for paper in no_minor_papers:
                ptype = paper["paper_type"]
                if ptype not in common_by_type:
                    common_by_type[ptype] = []
                common_by_type[ptype].append(paper)

            common_type_groups = []
            for t in TYPE_ORDER:
                if t in common_by_type:
                    common_type_groups.append({
                        "type":   t,
                        "label":  TYPE_LABELS.get(t, t),
                        "papers": common_by_type[t],
                    })
            for t in common_by_type:
                if t not in TYPE_ORDER:
                    common_type_groups.append({
                        "type":   t,
                        "label":  TYPE_LABELS.get(t, t),
                        "papers": common_by_type[t],
                    })

            ordered_groups.append({
                "minor":       None,
                "minor_label": "Common Papers",
                "type_groups": common_type_groups,
            })

        # Minor-specific groups
        for minor in sorted(minor_groups.keys()):
            by_type = minor_groups[minor]
            type_groups = []
            for t in TYPE_ORDER:
                if t in by_type:
                    type_groups.append({
                        "type":   t,
                        "label":  TYPE_LABELS.get(t, t),
                        "papers": by_type[t],
                    })
            for t in by_type:
                if t not in TYPE_ORDER:
                    type_groups.append({
                        "type":   t,
                        "label":  TYPE_LABELS.get(t, t),
                        "papers": by_type[t],
                    })
            ordered_groups.append({
                "minor":       minor,
                "minor_label": f"{minor} (Minor)",
                "type_groups": type_groups,
            })

    else:
        # No minors — flat grouping by paper_type
        by_type = {}
        for paper in papers:
            ptype = paper["paper_type"]
            if ptype not in by_type:
                by_type[ptype] = []
            by_type[ptype].append(paper)

        type_groups = []
        for t in TYPE_ORDER:
            if t in by_type:
                type_groups.append({
                    "type":   t,
                    "label":  TYPE_LABELS.get(t, t),
                    "papers": by_type[t],
                })
        for t in by_type:
            if t not in TYPE_ORDER:
                type_groups.append({
                    "type":   t,
                    "label":  TYPE_LABELS.get(t, t),
                    "papers": by_type[t],
                })

        ordered_groups = [{
            "minor":       None,
            "minor_label": None,
            "type_groups": type_groups,
        }]

    total_papers = len(papers)
    total_pdfs   = sum(len(p["pdfs"]) for p in papers)
    ready_pdfs   = sum(1 for p in papers for pdf in p["pdfs"] if pdf["status"] == "ready")

    return jsonify({
        "programme":  programme,
        "semester":   semester,
        "has_minors": has_minors,
        "minors":     minors,
        "groups":     ordered_groups,
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
# ADMIN — upload PDF
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
    language  = pdf_row.get("language", "English") or "English"
    folder    = os.path.dirname(file_path)
    os.makedirs(folder, exist_ok=True)
    file.save(file_path)

    update_pdf_status(pdf_name, "processing")
    process_book_task.delay(pdf_name, file_path, language)

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
    language = data.get("language", "English").strip() or "English"

    if not paper_id or not title:
        return jsonify({"error": "paper_id and title are required"}), 400

    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT p.*, pr.code, pr.name as prog_name
                FROM papers p
                JOIN programmes pr ON pr.id = p.programme_id
                WHERE p.id = %s
            """, (paper_id,))
            paper = cur.fetchone()

            if not paper:
                return jsonify({"error": "Paper not found"}), 404

            cur.execute(
                "SELECT COUNT(*) as cnt FROM pdfs WHERE paper_id = %s", (paper_id,)
            )
            existing  = cur.fetchone()["cnt"]
            block_num = existing + 1

            safe_title = title.replace(" ", "_").replace("/", "-")[:40]
            pdf_name   = f"{paper['code']}_S{paper['semester']}_P{paper_id}_Block{block_num}_{safe_title}"
            file_path  = build_upload_path(
                paper["code"], paper["semester"], paper["paper_name"], pdf_name
            )

            cur.execute("""
                INSERT INTO pdfs (paper_id, title, pdf_name, file_path, status, language)
                VALUES (%s, %s, %s, %s, 'pending', %s)
            """, (paper_id, title, pdf_name, file_path, language))
            conn.commit()
            new_id = cur.lastrowid

    finally:
        conn.close()

    return jsonify({
        "ok":        True,
        "id":        new_id,
        "pdf_name":  pdf_name,
        "title":     title,
        "status":    "pending",
        "language":  language,
        "file_path": file_path,
    })


# ─────────────────────────────────────────────────────────────
# ADMIN — remove a block (PDF slot)
# ─────────────────────────────────────────────────────────────

@library_bp.route("/api/admin/remove_block/<int:pdf_id>", methods=["DELETE"])
def remove_block(pdf_id):
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM pdfs WHERE id = %s", (pdf_id,))
            pdf = cur.fetchone()
            if not pdf:
                return jsonify({"error": "Block not found"}), 404

            file_path = pdf["file_path"]

            if file_path and os.path.exists(file_path):
                os.remove(file_path)

            for folder in ["summaries", "page_texts", "status"]:
                p = mirror_path(folder, file_path, pdf["pdf_name"])
                if os.path.exists(p):
                    os.remove(p)

            cur.execute("DELETE FROM pdfs WHERE id = %s", (pdf_id,))
            conn.commit()

    finally:
        conn.close()

    return jsonify({
        "ok":      True,
        "id":      pdf_id,
        "message": f"Block '{pdf['title']}' removed.",
    })


# ─────────────────────────────────────────────────────────────
# ADMIN — full programme+paper list for admin_library.html
# ─────────────────────────────────────────────────────────────

@library_bp.route("/api/admin/kkhsou_papers")
def api_kkhsou_papers():
    """
    Returns all programmes with their semesters and papers from the local DB.
    Shape: [ { id, code, name, semesters: [ { semester, papers: [...] } ] } ]
    """
    programmes = fetch_all_programmes()
    result = []
    for prog in programmes:
        conn = get_db()
        try:
            with conn.cursor() as cur:
                # Distinct semesters for this programme
                cur.execute(
                    "SELECT DISTINCT semester FROM papers WHERE programme_id=%s ORDER BY semester",
                    (prog["id"],)
                )
                semesters = [row["semester"] for row in cur.fetchall()]

                sem_list = []
                for sem in semesters:
                    cur.execute("""
                        SELECT id, paper_type, paper_name, minor
                        FROM papers
                        WHERE programme_id=%s AND semester=%s
                        ORDER BY paper_type, paper_name
                    """, (prog["id"], sem))
                    raw_papers = cur.fetchall()

                    papers_out = []
                    for p in raw_papers:
                        # Fetch PDFs for this paper
                        cur.execute(
                            "SELECT id, title, pdf_name, file_path, status, language FROM pdfs WHERE paper_id=%s ORDER BY id",
                            (p["id"],)
                        )
                        pdfs = [dict(row) for row in cur.fetchall()]

                        papers_out.append({
                            "id":         p["id"],
                            "paper_code": str(p["id"]),
                            "paper_name": p["paper_name"],
                            "group_code": p["paper_type"],
                            "group_name": TYPE_LABELS.get(p["paper_type"], p["paper_type"]),
                            "minor":      p["minor"],
                            "pdfs":       pdfs,
                        })

                    sem_list.append({"semester": sem, "papers": papers_out})

        finally:
            conn.close()

        result.append({
            "id":        prog["id"],
            "code":      prog["code"],
            "name":      prog["name"],
            "semesters": sem_list,
        })

    return jsonify(result)


# ─────────────────────────────────────────────────────────────
# ADMIN — add a new programme and pull its papers from KKHSOU
# ─────────────────────────────────────────────────────────────

@library_bp.route("/api/admin/add_programme", methods=["POST"])
def api_add_programme():
    data = request.get_json()
    code = (data.get("code") or "").strip().upper()
    name = (data.get("name") or "").strip()

    if not code:
        return jsonify({"error": "Programme code is required"}), 400

    # Upsert into local DB (api_prog_id=None — admin-added, not from student login)
    prog = upsert_programme_from_api(None, code, name or code)
    if not prog:
        return jsonify({"error": "Failed to create programme in database"}), 500

    pulled = 0
    errors = []

    if is_bachelor(code):
        # Degree programme — loop every minor × semester
        for minor in KKHSOU_MINORS:
            for sem in range(1, 7):
                try:
                    papers = fetch_program_papers_from_api(code, sem, minor=minor)
                    if papers:
                        count  = store_papers(prog["id"], sem, papers, code, minor=minor)
                        pulled += count
                except Exception as e:
                    errors.append(f"{minor} sem {sem}: {e}")
    else:
        # Masters/PG — 4 semesters, no minor needed
        for sem in range(1, 5):
            if semester_has_papers(prog["id"], sem):
                continue
            try:
                papers = fetch_program_papers_from_api(code, sem)
                if papers:
                    count  = store_papers(prog["id"], sem, papers, code)
                    pulled += count
            except Exception as e:
                errors.append(f"sem {sem}: {e}")

    return jsonify({
        "ok":      True,
        "id":      prog["id"],
        "code":    prog["code"],
        "name":    prog["name"],
        "pulled":  pulled,
        "errors":  errors,
        "message": f"Programme '{code}' ready. {pulled} papers synced.",
    })


# ─────────────────────────────────────────────────────────────
# ADMIN — mark ready manually
# ─────────────────────────────────────────────────────────────

@library_bp.route("/api/admin/mark_ready/<pdf_name>", methods=["POST"])
def mark_ready(pdf_name):
    update_pdf_status(pdf_name, "ready")
    return jsonify({"ok": True, "pdf_name": pdf_name, "status": "ready"})


# ─────────────────────────────────────────────────────────────
# ADMIN — remove a programme and all its papers/PDFs
# ─────────────────────────────────────────────────────────────

@library_bp.route("/api/admin/remove_programme/<int:prog_id>", methods=["DELETE"])
def remove_programme(prog_id):
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM programmes WHERE id=%s", (prog_id,))
            prog = cur.fetchone()
            if not prog:
                return jsonify({"error": "Programme not found"}), 404

            # Get all PDFs for this programme to delete files
            cur.execute("""
                SELECT pdfs.id, pdfs.pdf_name, pdfs.file_path
                FROM pdfs
                JOIN papers ON papers.id = pdfs.paper_id
                WHERE papers.programme_id = %s
            """, (prog_id,))
            pdfs = cur.fetchall()


            # Delete files from disk
            for pdf in pdfs:
                fp = pdf["file_path"]
                if fp and os.path.exists(fp):
                    os.remove(fp)
                for folder in ["summaries", "page_texts", "status"]:
                    p = mirror_path(folder, fp, pdf["pdf_name"])
                    if os.path.exists(p):
                        os.remove(p)

            # Delete DB rows (cascade: pdfs → papers → programme)
            cur.execute("""
                DELETE pdfs FROM pdfs
                JOIN papers ON papers.id = pdfs.paper_id
                WHERE papers.programme_id = %s
            """, (prog_id,))
            cur.execute("DELETE FROM papers WHERE programme_id=%s", (prog_id,))
            cur.execute("DELETE FROM programmes WHERE id=%s", (prog_id,))
            conn.commit()

    finally:
        conn.close()

    return jsonify({
        "ok":      True,
        "message": f"Programme '{prog['code']}' and all its data removed.",
    })