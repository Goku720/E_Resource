import os
import re
import json
import fitz
from flask import Flask, render_template, request, jsonify, redirect, url_for, session, send_from_directory
from database import fetch_pdf_by_name, get_student, init_db, log_login, log_logout
from tasks import process_book_task, summarize_with_chunks
from topic_extractor import extract_topics
from video_recommender import search_videos
from library_routes import library_bp
from qa_route import qa_bp
from paper_sync import sync_papers_for_student
from path_utils import mirror_path
from config import (
    UPLOAD_FOLDER, SUMMARY_FOLDER, PAGE_TEXT_FOLDER,
    STATUS_FOLDER, SECRET_KEY, KKHSOU_API_BASE, KKHSOU_API_KEY, USE_FAKE_LOGIN
)

app = Flask(__name__)
app.register_blueprint(library_bp)
app.register_blueprint(qa_bp)
app.secret_key = SECRET_KEY

init_db()   # creates all tables if they don't exist

# ── Folders ──────────────────────────────────────────────────
os.makedirs(STATUS_FOLDER,    exist_ok=True)
os.makedirs(UPLOAD_FOLDER,    exist_ok=True)
os.makedirs(SUMMARY_FOLDER,   exist_ok=True)
os.makedirs(PAGE_TEXT_FOLDER, exist_ok=True)


@app.after_request
def add_no_cache_headers(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response



# =========================================================
# PDF FILE SERVING
# =========================================================

@app.route("/pdf/<path:pdf_name>")
def serve_pdf(pdf_name):
    if "user" not in session:
        return redirect(url_for("login"))
    pdf_row = fetch_pdf_by_name(pdf_name)
    if not pdf_row:
        return f"PDF not found in database: {pdf_name}", 404
    abs_path = pdf_row["file_path"]
    if not os.path.isfile(abs_path):
        return f"PDF file missing on disk: {abs_path}", 404
    return send_from_directory(os.path.dirname(abs_path), os.path.basename(abs_path))


@app.route("/pdf_info/<pdf_name>")
def pdf_info(pdf_name):
    pdf_row = fetch_pdf_by_name(pdf_name)
    if not pdf_row or not pdf_row.get("file_path"):
        return jsonify({"pages": 0})
    pdf_path = pdf_row["file_path"]
    if not os.path.exists(pdf_path):
        return jsonify({"pages": 0})
    doc = fitz.open(pdf_path)
    return jsonify({"pages": len(doc)})


# =========================================================
# ADMIN
# =========================================================

@app.route("/admin", methods=["GET"])
def admin_page():
    if not session.get("is_admin"):
        return redirect(url_for("login"))
    return render_template("admin.html")




# =========================================================
# SUMMARY API
# =========================================================

@app.route("/summary_json/<path:pdf_name>")
def summary_json(pdf_name):
    pdf_row = fetch_pdf_by_name(pdf_name)
    file_path = pdf_row["file_path"] if pdf_row else None
    path = mirror_path(SUMMARY_FOLDER, file_path, pdf_name)
    flat = os.path.join(SUMMARY_FOLDER, f"{pdf_name}.json")
    for p in [path, flat]:
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                return jsonify(json.load(f))
    return jsonify({"global_summary": "", "sections": {}})


# =========================================================
# PAGE TEXT API
# =========================================================

@app.route("/page_text/<path:pdf_name>/<int:page>")
def get_page_text(pdf_name, page):
    pdf_row = fetch_pdf_by_name(pdf_name)
    file_path = pdf_row["file_path"] if pdf_row else None
    path = mirror_path(PAGE_TEXT_FOLDER, file_path, pdf_name)
    flat = os.path.join(PAGE_TEXT_FOLDER, f"{pdf_name}.json")
    for p in [path, flat]:
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                data = json.load(f)
            return jsonify({"text": data.get(str(page), "")})
    return jsonify({"text": ""})




# =========================================================
# AI VIDEO API
# =========================================================

@app.route("/ai_videos", methods=["POST"])
def ai_videos():
    data = request.json
    text = data.get("text", "")

    if not text or len(text.strip()) < 30:
        return jsonify({
            "topics":  [],
            "videos":  [],
            "message": "Not enough readable text found on this page.",
        })

    cleaned_text = " ".join(text.split())[:2000]
    topics       = extract_topics(cleaned_text)

    if not topics:
        words          = cleaned_text.split()
        fallback_topic = " ".join(words[:8]) if len(words) >= 8 else cleaned_text
        topics         = [fallback_topic]

    topics = list(dict.fromkeys([t.strip() for t in topics if t.strip()]))[:3]

    all_videos = []
    for topic in topics:
        try:
            videos = search_videos(topic)
            if videos:
                for v in videos:
                    v["matched_topic"] = topic
                all_videos.extend(videos)
        except Exception as e:
            print(f"Video search failed for topic '{topic}': {e}")

    unique_videos = []
    seen_urls     = set()
    for v in all_videos:
        url   = v.get("url", "").strip()
        title = v.get("title", "").strip()
        if url and url not in seen_urls:
            seen_urls.add(url)
            unique_videos.append({
                "title":         title,
                "url":           url,
                "matched_topic": v.get("matched_topic", ""),
            })

    unique_videos = unique_videos[:6]

    return jsonify({
        "topics":  topics,
        "videos":  unique_videos,
        "message": "success" if unique_videos else "No matching KKHSOU videos found.",
    })


# =========================================================
# PROCESSING STATUS
# =========================================================

@app.route("/processing_status/<path:pdf_name>")
def processing_status(pdf_name):
    pdf_row = fetch_pdf_by_name(pdf_name)
    file_path = pdf_row["file_path"] if pdf_row else None
    path = mirror_path(STATUS_FOLDER, file_path, pdf_name)
    flat = os.path.join(STATUS_FOLDER, f"{pdf_name}.json")
    for p in [path, flat]:
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                return jsonify(json.load(f))
    return jsonify({"status": "not_found", "progress": 0, "message": "No processing status found."})


# =========================================================
# FLIPBOOK / VIEWER
# =========================================================

@app.route("/flipbook/<pdf_name>")
def flipbook_view(pdf_name):
    if "user" not in session:
        return redirect(url_for("login"))
    return render_template(
        "flipbook.html",
        pdf_name=pdf_name,
        file_path=pdf_name,
        preview=False,
        guest=False,
    )


@app.route("/preview/<path:pdf_name>")
def preview(pdf_name):
    return render_template(
        "flipbook.html",
        pdf_name=pdf_name,
        file_path=f"{pdf_name}.pdf",
        preview=True,
        guest=True,
    )


# =========================================================
# KKHSOU API — student auth helper
# =========================================================

def kkhsou_student_login(mobile_no, password):
    import requests as _requests
    url  = f"{KKHSOU_API_BASE}/api/v1/student/login"
    resp = _requests.post(
        url,
        json={"mobile_no": mobile_no, "password": password},
        headers={"Content-Type": "application/json", "X-API-KEY": KKHSOU_API_KEY},
        timeout=10,
    )
    body = resp.json()
    if body.get("status") == "success" and body.get("data"):
        return body["data"]
    return None


# =========================================================
# LOGIN / LOGOUT
# =========================================================

@app.route("/")
def index():
    return redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    
    if session.get("user"):
        if session.get("is_admin"):
            return redirect("/admin")
        return redirect("/my-courses")


    if request.method == "POST":
        mobile_or_user = request.form["username"].strip()
        password       = request.form["password"].strip()

        # ── Admin: local DB check ──────────────────────────

        admin = get_student(mobile_or_user)
        if admin and admin["programme_id"] is None and admin["password"] == password:
            session["user"]         = admin["username"]
            session["full_name"]    = admin["full_name"]
            session["programme_id"] = None
            session["semester"]     = None
            session["is_admin"]     = True
            session["access_token"] = None

            log_id = log_login(
                username   = admin["username"],
                full_name  = admin["full_name"],
                programme  = "Admin",
                semester   = None,
                ip_address = request.remote_addr,
            )
            session["log_id"] = log_id

            return redirect("/admin")

        # ── Fake student login (offline/dev testing) ────────
        if USE_FAKE_LOGIN:
            fake = get_student(mobile_or_user)
            if not fake or fake["password"] != password:
                return render_template("login.html",
                                       error="Invalid mobile number or password.")

            session["user"]         = fake["username"]
            session["full_name"]    = fake["full_name"]
            session["programme_id"] = fake["programme_id"]
            session["semester"]     = fake["semester"]
            session["is_admin"]     = False
            session["access_token"] = None
            session["enrollments"]  = []

            log_id = log_login(
                username   = fake["username"],
                full_name  = fake["full_name"],
                programme  = str(fake["programme_id"]),
                semester   = fake["semester"],
                ip_address = request.remote_addr,
            )
            session["log_id"] = log_id

            return redirect("/my-courses")


        # ── Student: KKHSOU API ──────────────────────────
        try:
            data = kkhsou_student_login(mobile_or_user, password)
        except Exception:
            return render_template("login.html",
                                   error="Could not reach the student server. Please try again.")

        if not data:
            return render_template("login.html",
                                   error="Invalid mobile number or password.")

        student     = data.get("student", {})
        enrollments = data.get("enrollments", [])
        token       = data.get("access_token", "")
        primary     = enrollments[0] if enrollments else {}

        api_prog_id   = primary.get("program_id")
        prog_code     = primary.get("program_code", "")
        prog_name     = primary.get("program_name", "")
        semester      = primary.get("current_semester")
        enrollment_no = primary.get("enrollment_no", "")

        # Auto-register programme if new, then get local id
        from database import upsert_programme_from_api
        local_prog    = upsert_programme_from_api(api_prog_id, prog_code, prog_name) if api_prog_id else None
        local_prog_id = local_prog["id"] if local_prog else None

        # Sync papers if not already stored for this programme+semester
        from paper_sync import store_papers, semester_has_papers
        if enrollment_no and local_prog_id and semester:
            sync_papers_for_student(
                programme_id  = local_prog_id,
                prog_code     = prog_code,
                semester      = semester,
                enrollment_no = enrollment_no,
            )

        session["user"]         = str(student.get("mobile_no", mobile_or_user))
        session["full_name"]    = student.get("full_name", "Student")
        session["programme_id"] = local_prog_id
        session["semester"]     = semester
        session["is_admin"]     = False
        session["access_token"] = token
        session["enrollments"]  = enrollments

        log_id = log_login(
            username   = str(student.get("mobile_no", mobile_or_user)),
            full_name  = student.get("full_name", "Student"),
            programme  = prog_name,
            semester   = semester,
            ip_address = request.remote_addr,
        )
        session["log_id"] = log_id

        return redirect("/my-courses")

    return render_template("login.html", error=None)


@app.route("/logout")
def logout():
    log_id = session.get("log_id")
    if log_id:
        log_logout(log_id)
    session.clear()
    return redirect(url_for("login"))


# =========================================================
# MY COURSES
# =========================================================

@app.route("/my-courses")
def my_courses():
    if "user" not in session:
        return redirect(url_for("login"))
    if session.get("is_admin"):
        return redirect("/admin")
    return render_template("my_courses.html")


@app.route("/api/my-info")
def api_my_info():
    if "user" not in session:
        return jsonify({"error": "not logged in"}), 401

    prog_id     = session.get("programme_id")
    enrollments = session.get("enrollments", [])

    programme = None
    if enrollments:
        primary   = enrollments[0]
        programme = {
            "id":   session.get("programme_id"),   # local id
            "code": primary.get("program_code"),
            "name": primary.get("program_name"),
        }
    elif prog_id:
        from database import fetch_programme_by_id
        programme = fetch_programme_by_id(prog_id)

    return jsonify({
        "username":     session.get("user"),
        "full_name":    session.get("full_name", "Student"),
        "programme_id": prog_id,
        "semester":     session.get("semester"),
        "is_admin":     session.get("is_admin", False),
        "programme":    programme,
        "enrollments":  enrollments,
    })


# =========================================================
# BOOKS (legacy list page)
# =========================================================

@app.route("/books")
def books():
    if not os.path.exists(SUMMARY_FOLDER):
        return render_template("books.html", books=[])
    files = os.listdir(SUMMARY_FOLDER)
    books_list = [f.replace(".json", "") for f in files if f.endswith(".json")]
    return render_template("books.html", books=books_list)



# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0")