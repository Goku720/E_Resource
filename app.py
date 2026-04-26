import os
import re
import json
import fitz
import pytesseract
from PIL import Image
from flask import Flask, render_template, request, jsonify, redirect, url_for, session, send_from_directory
from tasks import process_book_task

from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
from topic_extractor import extract_topics
from video_recommender import search_videos
from library_routes import library_bp
app = Flask(__name__)
app.register_blueprint(library_bp)
app.secret_key = "secret"

# ------------------ FOLDERS ------------------
UPLOAD_FOLDER = "uploads"
SUMMARY_FOLDER = "summaries"
PAGE_TEXT_FOLDER = "page_texts"
STATUS_FOLDER = "status"

os.makedirs(STATUS_FOLDER, exist_ok=True)
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(SUMMARY_FOLDER, exist_ok=True)
os.makedirs(PAGE_TEXT_FOLDER, exist_ok=True)

# ------------------ TESSERACT ------------------
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# ------------------ MODEL ------------------
model_name = "sshleifer/distilbart-cnn-12-6"
tokenizer = AutoTokenizer.from_pretrained(model_name)
model = AutoModelForSeq2SeqLM.from_pretrained(model_name)

# =========================================================
# OCR + TEXT CLEANING
# =========================================================
def is_text_good(text):
    if not text or len(text.strip()) < 80:
        return False

    words = text.split()

    if len(words) < 15:
        return False

    alpha_words = [w for w in words if any(ch.isalpha() for ch in w)]

    if len(alpha_words) < 10:
        return False

    return True


def clean_extracted_text(text):
    if not text:
        return ""

    lines = text.splitlines()
    cleaned = []

    for line in lines:
        line = line.strip()

        if not line:
            continue

        # remove obvious junk
        if re.fullmatch(r"\d+", line):
            continue

        if len(line) <= 2:
            continue

        if "www." in line.lower() or "http" in line.lower():
            continue

        if "kkhsou" in line.lower() and len(line.split()) <= 8:
            continue

        # remove excessive symbols
        line = re.sub(r'[^\w\s\.,;:()\-\+\=\*/%]', ' ', line)
        line = re.sub(r'\s+', ' ', line).strip()

        if len(line) < 3:
            continue

        cleaned.append(line)

    # remove repeated lines (common OCR header/footer issue)
    freq = {}
    for line in cleaned:
        freq[line] = freq.get(line, 0) + 1

    cleaned_final = []
    for line in cleaned:
        # if a short line repeats too often, likely header/footer
        if freq[line] > 3 and len(line.split()) <= 8:
            continue
        cleaned_final.append(line)

    return "\n".join(cleaned_final).strip()


def extract_text_hybrid(pdf_path):
    doc = fitz.open(pdf_path)
    page_texts = []

    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        text = page.get_text("text")

        if is_text_good(text):
            print(f"[SKIP OCR] Text layer used on page {page_num + 1}")
        else:
            print(f"[OCR] OCR used on page {page_num + 1}")
            pix = page.get_pixmap(dpi=200)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            text = pytesseract.image_to_string(img)

        text = clean_extracted_text(text)

        page_texts.append({
            "page": page_num + 1,
            "text": text
        })

    return page_texts

# =========================================================
# SUMMARIZATION
# =========================================================
def chunk_text(text, max_words=350):
    words = text.split()
    return [" ".join(words[i:i+max_words]) for i in range(0, len(words), max_words)]


def summarize_with_chunks(text):
    if not text or len(text.strip()) < 80:
        return "Not enough readable text found for summarization."

    chunks = chunk_text(text, 350)
    summaries = []

    for chunk in chunks[:3]:
        try:
            inputs = tokenizer(
                chunk,
                return_tensors="pt",
                truncation=True,
                max_length=512
            )

            summary_ids = model.generate(
                inputs["input_ids"],
                num_beams=3,
                max_length=90,
                min_length=20,
                early_stopping=True
            )

            summaries.append(tokenizer.decode(summary_ids[0], skip_special_tokens=True))
        except Exception as e:
            print("Summarization error:", e)

    final = " ".join(summaries).strip()
    return final if final else "Could not generate summary."


def is_summary_reliable(summary_text):
    if not summary_text or len(summary_text.strip()) < 25:
        return False

    if summary_text.lower().count("the") > 20 and len(summary_text.split()) < 30:
        return False

    weird_chars = re.findall(r'[^A-Za-z0-9\s\.,;:()\-\']', summary_text)
    if len(weird_chars) > 20:
        return False

    return True

# =========================================================
# SECTION DETECTION
# =========================================================
def is_heading(line):
    clean = line.strip()

    if len(clean) < 4:
        return False

    words = clean.split()

    # ALL CAPS
    if clean.isupper() and 1 <= len(words) <= 12:
        return True

    # Numbered heading
    if re.match(r"^\d+(\.\d+)*\s+[A-Za-z].*", clean):
        return True

    # Title-case short heading
    if 2 <= len(words) <= 8 and clean.istitle():
        return True

    return False


def split_sections_with_pages(page_texts):
    sections = {}
    current_section = "INTRODUCTION"

    for p in page_texts:
        text = p["text"]
        page_num = p["page"]
        lines = text.split("\n")

        for line in lines:
            clean = line.strip()
            if not clean:
                continue

            if is_heading(clean):
                current_section = clean
                if current_section not in sections:
                    sections[current_section] = {"text": "", "pages": []}

            if current_section not in sections:
                sections[current_section] = {"text": "", "pages": []}

            sections[current_section]["text"] += clean + " "
            sections[current_section]["pages"].append(page_num)

    return sections

# =========================================================
# CONTENT ANALYSIS
# =========================================================
def detect_content_type(text):
    t = text.lower()
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    bullet_count = sum(1 for line in lines if re.match(r"^(\d+\.|[-•*])", line))

    code_keywords = ["int ", "float ", "printf", "cout", "cin", "public static", "def ", "class ", "{", "}", "();", "return "]
    if any(k in text for k in code_keywords):
        return "code"

    algorithm_keywords = ["algorithm", "step 1", "step 2", "pseudo code", "pseudocode", "flowchart", "binary search", "linear search", "sorting", "searching"]
    if any(k in t for k in algorithm_keywords):
        return "algorithm"

    comparison_keywords = ["difference between", "compare", "comparison", "vs", "versus"]
    if any(k in t for k in comparison_keywords):
        return "comparison"

    formula_patterns = [
        r"[A-Za-z]\s*=\s*[A-Za-z0-9+\-*/()]+",
        r"\bformula\b",
        r"\bequation\b",
        r"\bmean\s*=\b",
        r"\bf\s*=\s*ma\b"
    ]
    for pat in formula_patterns:
        if re.search(pat, text):
            return "formula"

    if bullet_count >= 3:
        if any(k in t for k in ["procedure", "process", "steps", "method", "how to"]):
            return "steps"
        return "list"

    if any(k in t for k in ["is defined as", "can be defined as", "refers to", "means", "definition"]):
        return "definition"

    if len(text.split()) > 120:
        return "theory"

    return "descriptive"


def extract_title_fallback(section_title, text):
    if section_title and section_title.strip():
        return section_title.strip()

    lines = [line.strip() for line in text.split("\n") if line.strip()]
    return lines[0] if lines else "Untitled Topic"


def extract_bullets(text, max_items=5):
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    bullets = []

    for line in lines:
        if re.match(r"^(\d+\.|[-•*])", line):
            clean = re.sub(r"^(\d+\.|[-•*])\s*", "", line).strip()
            if len(clean) > 3:
                bullets.append(clean)

    if not bullets:
        sentences = re.split(r'(?<=[.!?])\s+', text)
        for s in sentences:
            s = s.strip()
            if len(s) > 25:
                bullets.append(s)

    return bullets[:max_items]


def extract_formula_lines(text, max_items=4):
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    formulas = []

    for line in lines:
        if "=" in line and len(line) < 100:
            formulas.append(line)

    return formulas[:max_items]


def extract_code_lines(text, max_items=10):
    lines = [line.rstrip() for line in text.split("\n")]
    code_lines = []

    for line in lines:
        if any(k in line for k in ["{", "}", ";", "def ", "class ", "return ", "printf", "cout", "int ", "float ", "for(", "while("]):
            if line.strip():
                code_lines.append(line)

    return code_lines[:max_items]


def extract_definitions(text, max_items=4):
    sentences = re.split(r'(?<=[.!?])\s+', text)
    defs = []

    for s in sentences:
        s = s.strip()
        if len(s) < 20:
            continue

        if any(k in s.lower() for k in ["is defined as", "can be defined as", "refers to", "means", "is called"]):
            defs.append({
                "term": "",
                "meaning": s
            })

    return defs[:max_items]


def extract_examples(text, max_items=4):
    sentences = re.split(r'(?<=[.!?])\s+', text)
    examples = []

    for s in sentences:
        s = s.strip()
        if len(s) < 20:
            continue

        if any(k in s.lower() for k in ["for example", "for instance", "e.g.", "example"]):
            examples.append(s)

    return examples[:max_items]


def generate_exam_questions(title, content_type):
    questions = []

    if title and title.strip():
        questions.append(f"What is {title}?")
        questions.append(f"Explain {title}.")

    if content_type == "comparison":
        questions.append(f"Compare the concepts related to {title}.")
    elif content_type in ["steps", "algorithm"]:
        questions.append(f"Write the steps of {title}.")
    elif content_type == "formula":
        questions.append(f"Write the formula and explain {title}.")
    else:
        questions.append(f"Write a short note on {title}.")

    return list(dict.fromkeys(questions))[:4]


def build_smart_summary(section_title, text):
    content_type = detect_content_type(text)
    short_text = text[:2200]
    summary_text = summarize_with_chunks(short_text)

    if not is_summary_reliable(summary_text):
        summary_text = "This section contains partially readable educational content but needs cleaner extraction."

    title = extract_title_fallback(section_title, text)
    key_points = extract_bullets(text, 6)
    steps = extract_bullets(text, 6) if content_type in ["steps", "algorithm"] else []
    formulae = extract_formula_lines(text, 4)
    code_snippet = extract_code_lines(text, 10)
    comparison_points = extract_bullets(text, 6) if content_type == "comparison" else []
    definitions = extract_definitions(text, 4)
    examples = extract_examples(text, 4)

    simple_explanation = summary_text
    if len(summary_text.split()) > 25:
        simple_explanation = " ".join(summary_text.split()[:25]) + "."

    short_answer = summary_text
    long_answer = summary_text
    if key_points:
        long_answer += "\n\nImportant points:\n• " + "\n• ".join(key_points[:5])

    return {
        "type": content_type,
        "title": title,
        "summary_text": summary_text,
        "main_idea": summary_text,
        "simple_explanation": simple_explanation,
        "definitions": definitions,
        "key_points": key_points,
        "steps": steps,
        "formulae": formulae,
        "code_snippet": code_snippet,
        "examples": examples,
        "comparison_points": comparison_points,
        "exam_questions": generate_exam_questions(title, content_type),
        "short_answer": short_answer,
        "long_answer": long_answer
    }

# =========================================================
# SEARCH / RETRIEVAL HELPERS
# =========================================================
def normalize_for_search(text):
    return re.sub(r'[^a-z0-9\s]', ' ', text.lower()).strip()


def detect_intent(question):
    q = normalize_for_search(question)

    if any(x in q for x in ["what is", "define", "meaning of"]):
        return "definition"
    if any(x in q for x in ["explain", "describe", "elaborate"]):
        return "explanation"
    if any(x in q for x in ["step", "process", "procedure", "how"]):
        return "steps"
    if any(x in q for x in ["difference", "compare", "comparison", "vs", "versus"]):
        return "comparison"
    if any(x in q for x in ["formula", "equation", "law"]):
        return "formula"
    if any(x in q for x in ["example", "sample", "instance"]):
        return "example"
    if any(x in q for x in ["short note", "long answer", "exam", "5 marks", "10 marks", "2 marks"]):
        return "exam"
    if any(x in q for x in ["important", "point", "highlight"]):
        return "important_points"

    return "general"

def is_query_meaningful(question):
    q = normalize_for_search(question)

    if not q or len(q.strip()) < 3:
        return False

    words = [w for w in q.split() if len(w) >= 3]

    if len(words) == 0:
        return False

    # obvious nonsense / abusive / irrelevant junk
    blocked_words = {
        "fuck", "fucking", "shit", "bitch", "asshole", "sex", "porn",
        "random", "asdf", "qwerty", "xyz", "hello", "hi", "test"
    }

    if all(w in blocked_words for w in words):
        return False

    return True

def score_match(question, section, current_page=None):
    score = 0
    q = normalize_for_search(question)
    q_words = set(q.split())

    title = normalize_for_search(section.get("title", ""))
    main_idea = normalize_for_search(section.get("main_idea", ""))
    simple_explanation = normalize_for_search(section.get("simple_explanation", ""))
    key_points = normalize_for_search(" ".join(section.get("key_points", [])))
    steps = normalize_for_search(" ".join(section.get("steps", [])))
    comparison = normalize_for_search(" ".join(section.get("comparison_points", [])))
    examples = normalize_for_search(" ".join(section.get("examples", [])))
    formulae = normalize_for_search(" ".join(section.get("formulae", [])))
    definitions = normalize_for_search(" ".join([d.get("meaning", "") for d in section.get("definitions", [])]))

    all_text = f"{title} {main_idea} {simple_explanation} {key_points} {steps} {comparison} {examples} {formulae} {definitions}"

    for word in q_words:
        if len(word) < 3:
            continue

        if word in title:
            score += 8
        if word in definitions:
            score += 7
        if word in main_idea:
            score += 5
        if word in simple_explanation:
            score += 4
        if word in key_points:
            score += 3
        if word in steps:
            score += 3
        if word in comparison:
            score += 3
        if word in examples:
            score += 2
        if word in formulae:
            score += 3
        if word in all_text:
            score += 1

    if q in title:
        score += 15
    if q in definitions:
        score += 12
    if q in main_idea:
        score += 10
    if q in all_text:
        score += 6

    # page awareness
    if current_page is not None:
        start_page = section.get("start_page")
        end_page = section.get("end_page")

        if start_page and end_page:
            if start_page <= current_page <= end_page:
                score += 10
            elif abs(current_page - start_page) <= 2 or abs(current_page - end_page) <= 2:
                score += 4

    return score


def search_page_texts(question, pdf_name, current_page=None):
    page_text_path = os.path.join(PAGE_TEXT_FOLDER, f"{pdf_name}.json")
    if not os.path.exists(page_text_path):
        return None

    with open(page_text_path, encoding="utf-8") as f:
        page_data = json.load(f)

    q = normalize_for_search(question)
    q_words = [w for w in q.split() if len(w) >= 3]

    best_page = None
    best_score = -1
    best_text = ""

    for page_str, text in page_data.items():
        page_num = int(page_str)
        t = normalize_for_search(text)
        score = 0

        for word in q_words:
            if word in t:
                score += t.count(word) * 2

        if q in t:
            score += 10

        if current_page is not None:
            if page_num == current_page:
                score += 6
            elif abs(page_num - current_page) <= 2:
                score += 3

        if score > best_score:
            best_score = score
            best_page = page_num
            best_text = text

    if best_score <= 0:
        return None

    return {
        "page": best_page,
        "text": best_text[:1800],
        "score": best_score
    }


def build_answer_from_section(question, section, mode="detailed"):
    intent = detect_intent(question)

    if intent == "definition":
        if section.get("definitions"):
            return section["definitions"][0].get("meaning", section.get("main_idea", ""))

        if mode == "simple":
            return section.get("simple_explanation", section.get("main_idea", ""))
        return section.get("main_idea", "")

    if intent == "steps":
        if section.get("steps"):
            if mode == "bullet":
                return "• " + "\n• ".join(section["steps"][:6])
            return "Here are the main steps:\n• " + "\n• ".join(section["steps"][:6])

    if intent == "comparison":
        if section.get("comparison_points"):
            return "Here are the comparison points:\n• " + "\n• ".join(section["comparison_points"][:6])

    if intent == "formula":
        if section.get("formulae"):
            return "Relevant formula(s):\n• " + "\n• ".join(section["formulae"][:4])

    if intent == "example":
        if section.get("examples"):
            return "Example(s):\n• " + "\n• ".join(section["examples"][:4])

    if intent == "important_points":
        if section.get("key_points"):
            return "Important points:\n• " + "\n• ".join(section["key_points"][:6])

    if intent == "exam":
        if mode == "exam":
            return section.get("long_answer", section.get("main_idea", ""))
        return section.get("short_answer", section.get("main_idea", ""))

    # fallback modes
    if mode == "simple":
        return section.get("simple_explanation", section.get("main_idea", ""))

    if mode == "bullet":
        if section.get("key_points"):
            return "• " + "\n• ".join(section["key_points"][:6])
        return section.get("main_idea", "")

    if mode == "exam":
        return section.get("long_answer", section.get("main_idea", ""))

    return section.get("main_idea", section.get("summary_text", ""))


def build_answer_from_page_text(question, page_text, mode="detailed"):
    text = page_text.strip()
    if not text:
        return "I found a partial match in the book, but the page text was not readable enough."

    summary = summarize_with_chunks(text[:1800])

    if mode == "simple":
        return " ".join(summary.split()[:30]) + "."

    return summary


def generate_followups(section, intent):
    title = section.get("title", "this topic")
    suggestions = [
        f"Explain {title} simply",
        f"What are the important points of {title}?",
        f"Give an example of {title}"
    ]

    if section.get("steps"):
        suggestions.append(f"What are the steps of {title}?")

    if section.get("formulae"):
        suggestions.append(f"What is the formula of {title}?")

    if section.get("comparison_points"):
        suggestions.append(f"Compare concepts related to {title}")

    if intent != "exam":
        suggestions.append(f"Write a short note on {title}")

    return list(dict.fromkeys(suggestions))[:5]


def confidence_label(score):
    if score >= 35:
        return "high"
    if score >= 18:
        return "medium"
    return "low"

# =========================================================
# PDF FILE SERVING
# =========================================================
@app.route("/pdf/<pdf_name>")
def serve_pdf(pdf_name):
    filename = f"{pdf_name}.pdf"
    return send_from_directory(UPLOAD_FOLDER, filename)


@app.route("/pdf_info/<pdf_name>")
def pdf_info(pdf_name):
    pdf_path = os.path.join(UPLOAD_FOLDER, f"{pdf_name}.pdf")

    if not os.path.exists(pdf_path):
        return jsonify({"pages": 0})

    doc = fitz.open(pdf_path)
    return jsonify({"pages": len(doc)})

# =========================================================
# ADMIN
# =========================================================
@app.route("/admin", methods=["GET"])
def admin_page():
    return render_template("admin.html")


@app.route("/admin/upload", methods=["POST"])
def admin_upload():
    file = request.files["pdf"]

    if not file or file.filename == "":
        return jsonify({"error": "No PDF uploaded"}), 400

    pdf_name = file.filename.replace(".pdf", "")
    pdf_path = os.path.join(UPLOAD_FOLDER, file.filename)

    summary_path = os.path.join(SUMMARY_FOLDER, f"{pdf_name}.json")
    page_text_path = os.path.join(PAGE_TEXT_FOLDER, f"{pdf_name}.json")
    status_path = os.path.join(STATUS_FOLDER, f"{pdf_name}.json")

    if (
        os.path.exists(summary_path) and
        os.path.exists(page_text_path) and
        os.path.exists(pdf_path)
    ):
        return jsonify({
            "message": "Already processed. Skipping heavy processing.",
            "pdf_name": pdf_name,
            "skipped": True
        })

    # Save uploaded PDF
    file.save(pdf_path)

    # Initial status file
    with open(status_path, "w", encoding="utf-8") as f:
        json.dump({
            "status": "queued",
            "progress": 0,
            "message": "Book queued for background processing."
        }, f, ensure_ascii=False, indent=2)

    # Start background task
    process_book_task.delay(pdf_name, pdf_path)

    return jsonify({
        "message": "Upload successful. Processing started in background.",
        "pdf_name": pdf_name,
        "skipped": False,
        "background": True
    })

# =========================================================
# SUMMARY API
# =========================================================
@app.route("/summary_json/<pdf_name>")
def summary_json(pdf_name):
    path = os.path.join(SUMMARY_FOLDER, f"{pdf_name}.json")

    if not os.path.exists(path):
        return jsonify({"global_summary": "", "sections": {}})

    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    return jsonify(data)

# =========================================================
# PAGE TEXT API
# =========================================================
@app.route("/page_text/<pdf_name>/<int:page>")
def get_page_text(pdf_name, page):
    path = os.path.join(PAGE_TEXT_FOLDER, f"{pdf_name}.json")

    if not os.path.exists(path):
        return jsonify({"text": ""})

    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    return jsonify({
        "text": data.get(str(page), "")
    })

# =========================================================
# ASK THIS BOOK AI V2
# =========================================================
@app.route("/ask_book", methods=["POST"])
def ask_book():
    data = request.json
    pdf_name = data.get("pdf_name", "").strip()
    question = data.get("question", "").strip()
    current_page = data.get("current_page")
    mode = data.get("mode", "detailed").strip().lower()

    if mode not in ["simple", "detailed", "exam", "bullet"]:
        mode = "detailed"

    if not pdf_name or not question:
        return jsonify({
            "answer": "Missing book name or question.",
            "source_page": None,
            "matched_section": None,
            "confidence": "low",
            "followups": []
        }), 400

    # 🚫 Reject meaningless / junk queries
    if not is_query_meaningful(question):
        return jsonify({
            "answer": "I couldn’t find a relevant academic question in this book. Try asking about a topic or concept from the subject.",
            "source_page": None,
            "matched_section": None,
            "confidence": "low",
            "intent": "invalid",
            "mode": mode,
            "followups": [
                "What is this chapter about?",
                "Give important points from this page",
                "Explain the current topic"
            ]
        })

    summary_path = os.path.join(SUMMARY_FOLDER, f"{pdf_name}.json")

    if not os.path.exists(summary_path):
        return jsonify({
            "answer": "Summary file not found for this book.",
            "source_page": None,
            "matched_section": None,
            "confidence": "low",
            "followups": []
        }), 404

    with open(summary_path, encoding="utf-8") as f:
        summary_data = json.load(f)

    sections = summary_data.get("sections", {})
    intent = detect_intent(question)

    best_section = None
    best_score = -1
    for _, section in sections.items():
        score = score_match(question, section, current_page=current_page)

        if score > best_score:
            best_score = score
            best_section = section
    real_overlap = has_real_overlap(question, best_section) if best_section else 0

    # 🔍 Page-text fallback only if section match is weak
    page_fallback = None
    if (best_score < 18 and page_score < 18) or real_overlap == 0:

        # 🚫 HARD RELEVANCE FILTER
        # If both section and page matches are weak, reject
        page_score = page_fallback["score"] if page_fallback else 0

    if best_score < 18 and page_score < 18:
        return jsonify({
            "answer": "I couldn’t find a clearly relevant answer for that in this book. Try asking using a topic name, definition, process, formula, or exam-style question.",
            "source_page": None,
            "matched_section": None,
            "confidence": "low",
            "intent": intent,
            "mode": mode,
            "followups": [
                "What is this chapter about?",
                "Give important points from this page",
                "Explain the current topic",
                "Write a short note on this topic"
            ]
        })

    # If page text is stronger than section summary
    if page_fallback and page_fallback["score"] > best_score and page_fallback["score"] >= 18:
        answer = build_answer_from_page_text(question, page_fallback["text"], mode=mode)

        return jsonify({
            "answer": answer,
            "source_page": page_fallback["page"],
            "matched_section": "Matched Page Content",
            "confidence": confidence_label(page_fallback["score"]),
            "intent": intent,
            "mode": mode,
            "followups": [
                "Explain this simply",
                "Give important points",
                "Write a short note on this topic"
            ]
        })

    if not best_section:
        return jsonify({
            "answer": "I couldn’t find a relevant answer in this book.",
            "source_page": None,
            "matched_section": None,
            "confidence": "low",
            "intent": intent,
            "mode": mode,
            "followups": [
                "What is this chapter about?",
                "Give important points from this page"
            ]
        })

    answer = build_answer_from_section(question, best_section, mode=mode)
    followups = generate_followups(best_section, intent)

    return jsonify({
        "answer": answer,
        "source_page": best_section.get("start_page"),
        "matched_section": best_section.get("title", "Matched Section"),
        "confidence": confidence_label(best_score),
        "intent": intent,
        "mode": mode,
        "followups": followups
    })

def has_real_overlap(question, section):
    q_words = set([w for w in normalize_for_search(question).split() if len(w) >= 4])

    searchable = " ".join([
        section.get("title", ""),
        section.get("main_idea", ""),
        section.get("simple_explanation", ""),
        " ".join(section.get("key_points", [])),
        " ".join(section.get("steps", [])),
        " ".join(section.get("comparison_points", [])),
        " ".join(section.get("formulae", [])),
        " ".join(section.get("examples", []))
    ])

    searchable = normalize_for_search(searchable)
    overlap = [w for w in q_words if w in searchable]

    return len(overlap)    

# =========================================================
# AI VIDEO API
# =========================================================
@app.route("/ai_videos", methods=["POST"])
def ai_videos():
    data = request.json
    text = data.get("text", "")

    if not text or len(text.strip()) < 30:
        return jsonify({
            "topics": [],
            "videos": [],
            "message": "Not enough readable text found on this page."
        })

    cleaned_text = " ".join(text.split())
    cleaned_text = cleaned_text[:2000]

    topics = extract_topics(cleaned_text)

    if not topics or len(topics) == 0:
        words = cleaned_text.split()
        fallback_topic = " ".join(words[:8]) if len(words) >= 8 else cleaned_text
        topics = [fallback_topic]

    topics = [t.strip() for t in topics if t.strip()]
    topics = list(dict.fromkeys(topics))[:3]

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
    seen_urls = set()

    for v in all_videos:
        url = v.get("url", "").strip()
        title = v.get("title", "").strip()

        if url and url not in seen_urls:
            seen_urls.add(url)
            unique_videos.append({
                "title": title,
                "url": url,
                "matched_topic": v.get("matched_topic", "")
            })

    unique_videos = unique_videos[:6]

    return jsonify({
        "topics": topics,
        "videos": unique_videos,
        "message": "success" if unique_videos else "No matching KKHSOU videos found."
    })

# ======================================
# BG Processing
# ======================================

@app.route("/processing_status/<pdf_name>")
def processing_status(pdf_name):
    path = os.path.join(STATUS_FOLDER, f"{pdf_name}.json")

    if not os.path.exists(path):
        return jsonify({
            "status": "not_found",
            "progress": 0,
            "message": "No processing status found."
        })

    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    return jsonify(data)


# =========================================================
# FLIPBOOK / VIEWER
# =========================================================
@app.route("/flipbook/<pdf_name>")
def flipbook_view(pdf_name):
    if "user" not in session:
        return redirect(url_for("login"))

    return render_template("flipbook.html", pdf_name=pdf_name, preview=False)


@app.route("/preview/<pdf_name>")
def preview(pdf_name):
    return render_template("flipbook.html", pdf_name=pdf_name, preview=True)

# =========================================================
# LOGIN
# =========================================================
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
 
        if username == "student" and password == "123":
            session["user"] = username
            return redirect("/library")   # ← send to library instead of books
 
        return render_template("login.html", error="Invalid username or password.")
 
    return render_template("login.html", error=None)
 

@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect(url_for("login"))

# =========================================================
# BOOKS
# =========================================================
@app.route("/books")
def books():
    if not os.path.exists(SUMMARY_FOLDER):
        return render_template("books.html", books=[])

    files = os.listdir(SUMMARY_FOLDER)
    books = [f.replace(".json", "") for f in files if f.endswith(".json")]

    return render_template("books.html", books=books)

# =========================================================
# RUN
# =========================================================
if __name__ == "__main__":
    app.run(debug=True)