import os
import json
import fitz
import pytesseract
import re

from PIL import Image
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
from celery_app import celery

# ------------------ FOLDERS ------------------
UPLOAD_FOLDER = "uploads"
SUMMARY_FOLDER = "summaries"
PAGE_TEXT_FOLDER = "page_texts"
STATUS_FOLDER = "status"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(SUMMARY_FOLDER, exist_ok=True)
os.makedirs(PAGE_TEXT_FOLDER, exist_ok=True)
os.makedirs(STATUS_FOLDER, exist_ok=True)

# ------------------ TESSERACT ------------------
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# ------------------ MODEL ------------------
model_name = "sshleifer/distilbart-cnn-12-6"
tokenizer = AutoTokenizer.from_pretrained(model_name)
model = AutoModelForSeq2SeqLM.from_pretrained(model_name)

# =========================================================
# STATUS HELPERS
# =========================================================
def update_status(pdf_name, status, progress=0, message=""):
    path = os.path.join(STATUS_FOLDER, f"{pdf_name}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({
            "status": status,
            "progress": progress,
            "message": message
        }, f, ensure_ascii=False, indent=2)

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

        if re.fullmatch(r"\d+", line):
            continue

        if len(line) <= 2:
            continue

        if "www." in line.lower() or "http" in line.lower():
            continue

        if "kkhsou" in line.lower() and len(line.split()) <= 8:
            continue

        line = re.sub(r'[^\w\s\.,;:()\-\+\=\*/%]', ' ', line)
        line = re.sub(r'\s+', ' ', line).strip()

        if len(line) < 3:
            continue

        cleaned.append(line)

    freq = {}
    for line in cleaned:
        freq[line] = freq.get(line, 0) + 1

    cleaned_final = []
    for line in cleaned:
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

    if clean.isupper() and 1 <= len(words) <= 12:
        return True

    if re.match(r"^\d+(\.\d+)*\s+[A-Za-z].*", clean):
        return True

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
# MAIN BACKGROUND TASK
# =========================================================
@celery.task(bind=True)
def process_book_task(self, pdf_name, pdf_path):
    try:
        update_status(pdf_name, "extracting", 10, "Extracting text from PDF...")

        summary_path = os.path.join(SUMMARY_FOLDER, f"{pdf_name}.json")
        page_text_path = os.path.join(PAGE_TEXT_FOLDER, f"{pdf_name}.json")

        # 1. Extract text
        page_texts = extract_text_hybrid(pdf_path)

        update_status(pdf_name, "saving_pages", 30, "Saving page-wise text...")

        # 2. Save page-wise text
        page_text_dict = {str(p["page"]): p["text"] for p in page_texts}
        with open(page_text_path, "w", encoding="utf-8") as f:
            json.dump(page_text_dict, f, ensure_ascii=False, indent=2)

        update_status(pdf_name, "structuring", 50, "Detecting sections...")

        # 3. Detect sections
        sections = split_sections_with_pages(page_texts)
        smart_sections = {}

        total_sections = max(len(sections), 1)
        done_sections = 0

        for title, data in sections.items():
            text = data["text"]
            pages = sorted(list(set(data["pages"])))

            if len(text.strip()) < 250:
                continue

            smart_summary = build_smart_summary(title, text[:3000])

            smart_sections[title] = {
                "type": smart_summary["type"],
                "title": smart_summary["title"],
                "summary_text": smart_summary["summary_text"],
                "main_idea": smart_summary["main_idea"],
                "simple_explanation": smart_summary["simple_explanation"],
                "definitions": smart_summary["definitions"],
                "key_points": smart_summary["key_points"],
                "steps": smart_summary["steps"],
                "formulae": smart_summary["formulae"],
                "code_snippet": smart_summary["code_snippet"],
                "examples": smart_summary["examples"],
                "comparison_points": smart_summary["comparison_points"],
                "exam_questions": smart_summary["exam_questions"],
                "short_answer": smart_summary["short_answer"],
                "long_answer": smart_summary["long_answer"],
                "start_page": min(pages),
                "end_page": max(pages)
            }

            done_sections += 1
            progress = 50 + int((done_sections / total_sections) * 30)
            update_status(pdf_name, "summarizing", progress, f"Summarizing section {done_sections}/{total_sections}...")

        update_status(pdf_name, "global_summary", 90, "Generating global summary...")

        # 4. Global summary
        full_text = " ".join([p["text"] for p in page_texts])
        global_summary = summarize_with_chunks(full_text[:2500])

        if not is_summary_reliable(global_summary):
            global_summary = "This book contains educational content. Some sections may need better extraction for more reliable summaries."

        # 5. Save summary JSON
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump({
                "global_summary": global_summary,
                "sections": smart_sections
            }, f, ensure_ascii=False, indent=2)

        update_status(pdf_name, "ready", 100, "Book processing completed successfully.")
        
        from database import update_pdf_status
        update_pdf_status(pdf_name, "ready")

        return {
            "success": True,
            "pdf_name": pdf_name,
            "message": "Book processed successfully."
        }

    except Exception as e:
        update_status(pdf_name, "failed", 0, str(e))
        raise e