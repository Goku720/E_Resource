import os
import json
import fitz
import pytesseract
import re

import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import update_pdf_status
from path_utils import mirror_path

from PIL import Image
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
from celery_app import celery

# ------------------ FOLDERS ------------------
from config import UPLOAD_FOLDER, SUMMARY_FOLDER, PAGE_TEXT_FOLDER, STATUS_FOLDER

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(SUMMARY_FOLDER, exist_ok=True)
os.makedirs(PAGE_TEXT_FOLDER, exist_ok=True)
os.makedirs(STATUS_FOLDER, exist_ok=True)

# ------------------ TESSERACT ------------------
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# ------------------ LANGUAGE MAP ------------------
# Maps display language names to Tesseract lang codes.
# Requires the corresponding tessdata language packs installed.
# Download from: https://github.com/tesseract-ocr/tessdata
TESSERACT_LANG_MAP = {
    "English":   "eng",
    "Assamese":  "asm",
    "Bengali":   "ben",
    "Hindi":     "hin",
    "Bodo":      "brx",
    "Manipuri":  "mni",
    "Nepali":    "nep",
    "Urdu":      "urd",
    "Sanskrit":  "san",
    "Odia":      "ori",
}

def get_tess_lang(language):
    """Returns tesseract lang code, falls back to eng if pack not mapped."""
    return TESSERACT_LANG_MAP.get(language or "English", "eng")

# ------------------ MODEL REGISTRY ------------------
# Models are loaded lazily on first use and cached in memory.
# Keys match language names from TESSERACT_LANG_MAP.

_MODEL_CACHE = {}  # { model_name: (tokenizer, model) }

# Languages supported by ai4bharat/MultiIndicSentenceSummarizationSS
# Format: input must be "text </s> <2xx>" where xx = lang code below
INDIC_SUPPORTED = {
    # "Assamese": "as",
    # "Bengali":  "bn",
    "Hindi":    "hi",
    # "Odia":     "or",
    # "Sanskrit": "sa",
}

# Languages with no summarization model — OCR/text only
NO_SUMMARY_LANGS = {"Bodo", "Manipuri", "Urdu", "Assamese","Bengali","Sanskrit",}

def _get_model(language="English"):
    """
    Returns (tokenizer, model, lang_code) for the given language.
    lang_code is used by IndicBART input formatting.
    Returns (None, None, None) for unsupported languages.
    Loads lazily and caches.
    """
    if language in NO_SUMMARY_LANGS:
        print(f"[model] No summarization model for {language}, skipping.")
        return None, None, None

    if language in INDIC_SUPPORTED:
        model_name = "ai4bharat/MultiIndicSentenceSummarizationSS"
        lang_code  = INDIC_SUPPORTED[language]
    elif language == "Nepali":
        model_name = "GenzNepal/mt5-summarize-nepali"
        lang_code  = None
    else:
        # English and anything else falls back to distilbart
        model_name = "sshleifer/distilbart-cnn-12-6"
        lang_code  = None

    if model_name not in _MODEL_CACHE:
        print(f"[model] Loading {model_name} for language={language}…")
        tok = AutoTokenizer.from_pretrained(model_name)
        mdl = AutoModelForSeq2SeqLM.from_pretrained(model_name)
        _MODEL_CACHE[model_name] = (tok, mdl)
        print(f"[model] {model_name} loaded and cached.")

    tok, mdl = _MODEL_CACHE[model_name]
    return tok, mdl, lang_code



# =========================================================
# STATUS HELPERS
# =========================================================
def update_status(pdf_name, status, progress=0, message="", pdf_path=None):
    """
    Save status JSON mirroring the upload subfolder structure.
    Falls back to flat status/pdf_name.json if pdf_path not given.
    """
    path = mirror_path(STATUS_FOLDER, pdf_path, pdf_name)
    os.makedirs(os.path.dirname(path), exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        json.dump({
            "status":   status,
            "progress": progress,
            "message":  message
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


# Keywords that indicate non-content pages to skip
_JUNK_PAGE_PATTERNS = [
    r"^\s*table\s+of\s+contents?\s*$",
    r"^\s*contents?\s*$",
    r"^\s*index\s*$",
    r"^\s*acknowledgements?\s*$",
    r"^\s*acknowledgments?\s*$",
    r"^\s*preface\s*$",
    r"^\s*foreword\s*$",
    r"^\s*dedication\s*$",
    r"^\s*certificate\s*$",
    r"^\s*declaration\s*$",
    r"^\s*bibliography\s*$",
    r"^\s*references?\s*$",
    r"^\s*appendix\s*$",
    r"^\s*glossary\s*$",
    r"^\s*this\s+page\s+is\s+intentionally\s+left\s+blank",
    r"^\s*all\s+rights\s+reserved",
    r"^\s*copyright\s+",
    r"^\s*published\s+by\s+",
    r"^\s*printed\s+in\s+",
]

import re as _re

def is_junk_page(text):
    """
    Returns True if this page should be skipped during summarization.
    Detects: cover pages, TOC, certificates, blank pages, copyright, etc.
    Still saved to page_text for PDF viewer — just excluded from summarization.
    """
    if not text or len(text.strip()) < 30:
        return True  # blank / near-blank

    lines = [l.strip() for l in text.splitlines() if l.strip()]

    # Very few lines + short = likely a cover or decorative page
    if len(lines) <= 4 and len(text.split()) < 25:
        return True

    # Check first 5 lines for junk headings
    check_lines = lines[:5]
    for line in check_lines:
        for pat in _JUNK_PAGE_PATTERNS:
            if _re.search(pat, line.lower()):
                print(f"[SKIP PAGE] Junk pattern matched: {line!r}")
                return True

    # Page that's mostly numbers (TOC page numbers, index)
    words = text.split()
    if len(words) > 0:
        numeric = sum(1 for w in words if w.strip(".,)(-").isdigit())
        if numeric / len(words) > 0.5:
            return True

    return False


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


def extract_text_hybrid(pdf_path, tess_lang="eng"):
    doc = fitz.open(pdf_path)
    page_texts = []

    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        text = page.get_text("text")

        if is_text_good(text):
            print(f"[SKIP OCR] Text layer used on page {page_num + 1}")
        else:
            print(f"[OCR] OCR used on page {page_num + 1} (lang={tess_lang})")
            pix = page.get_pixmap(dpi=200)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            text = pytesseract.image_to_string(img, lang=tess_lang)

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


def summarize_with_chunks(text, language="English"):
    if not text or len(text.strip()) < 80:
        return "Not enough readable text found for summarization."

    tokenizer, model, lang_code = _get_model(language)

    if tokenizer is None or model is None:
        return f"Summarization is not available for {language}."

    chunks = chunk_text(text, 350)
    summaries = []

    for chunk in chunks[:3]:
        try:
            # IndicBART requires special input format: "text </s> <2xx>"
            if lang_code:
                chunk = f"{chunk} </s> <2{lang_code}>"

            inputs = tokenizer(
                chunk,
                return_tensors="pt",
                truncation=True,
                max_length=512
            )

            # IndicBART needs forced_bos_token_id for target language
            gen_kwargs = dict(
                num_beams=3,
                max_length=90,
                min_length=20,
                early_stopping=True,
            )
            if lang_code:
                tgt_token = f"<2{lang_code}>"
                if tgt_token in tokenizer.get_vocab():
                    gen_kwargs["forced_bos_token_id"] = tokenizer.convert_tokens_to_ids(tgt_token)

            summary_ids = model.generate(inputs["input_ids"], **gen_kwargs)
            summaries.append(tokenizer.decode(summary_ids[0], skip_special_tokens=True))

        except Exception as e:
            print(f"Summarization error ({language}):", e)

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


def build_smart_summary(section_title, text, language="English"):
    content_type = detect_content_type(text)
    short_text = text[:2200]
    summary_text = summarize_with_chunks(short_text, language=language)

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
def process_book_task(self, pdf_name, pdf_path, language="English"):
    try:
        tess_lang = get_tess_lang(language)
        print(f"[task] Processing '{pdf_name}' language={language} tess_lang={tess_lang}")

        # ── Build mirrored subfolder paths ──────────────────
        summary_path   = mirror_path(SUMMARY_FOLDER,   pdf_path, pdf_name)
        page_text_path = mirror_path(PAGE_TEXT_FOLDER, pdf_path, pdf_name)

        for p in [summary_path, page_text_path]:
            parent = os.path.dirname(p)
            if parent:
                os.makedirs(parent, exist_ok=True)
        # ────────────────────────────────────────────────────

        update_status(pdf_name, "extracting", 10, "Extracting text from PDF...", pdf_path)

        # 1. Extract text
        page_texts = extract_text_hybrid(pdf_path, tess_lang=tess_lang)
 
        update_status(pdf_name, "saving_pages", 30, "Saving page-wise text...", pdf_path)
 
        # 2. Save page-wise text
        page_text_dict = {str(p["page"]): p["text"] for p in page_texts}
        with open(page_text_path, "w", encoding="utf-8") as f:
            json.dump(page_text_dict, f, ensure_ascii=False, indent=2)
 
        update_status(pdf_name, "structuring", 50, "Detecting sections...", pdf_path)

        # 3. Filter out junk pages before section detection
        content_pages = [p for p in page_texts if not is_junk_page(p["text"])]
        skipped = len(page_texts) - len(content_pages)
        if skipped:
            print(f"[task] Skipped {skipped} junk page(s) from summarization.")

        # 3. Detect sections
        sections = split_sections_with_pages(content_pages)
        smart_sections = {}
 
        total_sections = max(len(sections), 1)
        done_sections  = 0
 
        for title, data in sections.items():
            text  = data["text"]
            pages = sorted(list(set(data["pages"])))
 
            if len(text.strip()) < 250:
                continue
 
            smart_summary = build_smart_summary(title, text[:3000], language=language)
 
            smart_sections[title] = {
                "type":               smart_summary["type"],
                "title":              smart_summary["title"],
                "summary_text":       smart_summary["summary_text"],
                "main_idea":          smart_summary["main_idea"],
                "simple_explanation": smart_summary["simple_explanation"],
                "definitions":        smart_summary["definitions"],
                "key_points":         smart_summary["key_points"],
                "steps":              smart_summary["steps"],
                "formulae":           smart_summary["formulae"],
                "code_snippet":       smart_summary["code_snippet"],
                "examples":           smart_summary["examples"],
                "comparison_points":  smart_summary["comparison_points"],
                "exam_questions":     smart_summary["exam_questions"],
                "short_answer":       smart_summary["short_answer"],
                "long_answer":        smart_summary["long_answer"],
                "start_page":         min(pages),
                "end_page":           max(pages)
            }
 
            done_sections += 1
            progress = 50 + int((done_sections / total_sections) * 30)
            update_status(pdf_name, "summarizing", progress,
                          f"Summarizing section {done_sections}/{total_sections}...", pdf_path)
 
        update_status(pdf_name, "global_summary", 90, "Generating global summary...", pdf_path)
 
        # 4. Global summary
        full_text      = " ".join([p["text"] for p in page_texts])
        global_summary = summarize_with_chunks(full_text[:2500], language=language)
 
        if not is_summary_reliable(global_summary):
            global_summary = "This book contains educational content. Some sections may need better extraction for more reliable summaries."
 
        # 5. Save summary JSON
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump({
                "global_summary": global_summary,
                "sections":       smart_sections
            }, f, ensure_ascii=False, indent=2)
 
        update_status(pdf_name, "ready", 100,
                      "Book processing completed successfully.", pdf_path)
        update_pdf_status(pdf_name, "ready")
 
        return {
            "success":  True,
            "pdf_name": pdf_name,
            "message":  "Book processed successfully."
        }
 
    except Exception as e:
        update_status(pdf_name, "failed", 0, str(e), pdf_path)
        raise e