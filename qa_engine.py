import os
import json
import re
from config import PAGE_TEXT_FOLDER
from tasks import summarize_with_chunks


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
    blocked_words = {
        "fuck", "fucking", "shit", "bitch", "asshole", "sex", "porn",
        "random", "asdf", "qwerty", "xyz", "hello", "hi", "test"
    }
    if all(w in blocked_words for w in words):
        return False
    return True


def score_match(question, section, current_page=None):
    score   = 0
    q       = normalize_for_search(question)
    q_words = set(q.split())

    title              = normalize_for_search(section.get("title", ""))
    main_idea          = normalize_for_search(section.get("main_idea", ""))
    simple_explanation = normalize_for_search(section.get("simple_explanation", ""))
    key_points         = normalize_for_search(" ".join(section.get("key_points", [])))
    steps              = normalize_for_search(" ".join(section.get("steps", [])))
    comparison         = normalize_for_search(" ".join(section.get("comparison_points", [])))
    examples           = normalize_for_search(" ".join(section.get("examples", [])))
    formulae           = normalize_for_search(" ".join(section.get("formulae", [])))
    definitions        = normalize_for_search(" ".join([d.get("meaning", "") for d in section.get("definitions", [])]))

    all_text = f"{title} {main_idea} {simple_explanation} {key_points} {steps} {comparison} {examples} {formulae} {definitions}"

    for word in q_words:
        if len(word) < 3:
            continue
        if word in title:              score += 8
        if word in definitions:        score += 7
        if word in main_idea:          score += 5
        if word in simple_explanation: score += 4
        if word in key_points:         score += 3
        if word in steps:              score += 3
        if word in comparison:         score += 3
        if word in examples:           score += 2
        if word in formulae:           score += 3
        if word in all_text:           score += 1

    if q in title:       score += 15
    if q in definitions: score += 12
    if q in main_idea:   score += 10
    if q in all_text:    score += 6

    if current_page is not None:
        start_page = section.get("start_page")
        end_page   = section.get("end_page")
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

    q       = normalize_for_search(question)
    q_words = [w for w in q.split() if len(w) >= 3]

    best_page  = None
    best_score = -1
    best_text  = ""

    for page_str, text in page_data.items():
        page_num = int(page_str)
        t        = normalize_for_search(text)
        score    = 0
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
            best_page  = page_num
            best_text  = text

    if best_score <= 0:
        return None

    return {"page": best_page, "text": best_text[:1800], "score": best_score}


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
    title       = section.get("title", "this topic")
    suggestions = [
        f"Explain {title} simply",
        f"What are the important points of {title}?",
        f"Give an example of {title}",
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


def has_real_overlap(question, section):
    q_words    = set([w for w in normalize_for_search(question).split() if len(w) >= 4])
    searchable = " ".join([
        section.get("title", ""),
        section.get("main_idea", ""),
        section.get("simple_explanation", ""),
        " ".join(section.get("key_points", [])),
        " ".join(section.get("steps", [])),
        " ".join(section.get("comparison_points", [])),
        " ".join(section.get("formulae", [])),
        " ".join(section.get("examples", [])),
    ])
    searchable = normalize_for_search(searchable)
    overlap    = [w for w in q_words if w in searchable]
    return len(overlap)

