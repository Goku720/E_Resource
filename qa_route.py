import os 
import json
from flask import Blueprint, request, jsonify
from database import fetch_pdf_by_name
from path_utils import mirror_path
from config import SUMMARY_FOLDER
from qa_engine import (
    is_query_meaningful,
    detect_intent,
    score_match,
    search_page_texts,
    build_answer_from_section,
    build_answer_from_page_text,
    generate_followups,
    confidence_label,
)

qa_bp = Blueprint("qa", __name__)

# =========================================================
# ASK THIS BOOK AI
# =========================================================

@qa_bp.route("/ask_book", methods=["POST"])
def ask_book():
    data         = request.json
    pdf_name     = data.get("pdf_name", "").strip()
    question     = data.get("question", "").strip()
    current_page = data.get("current_page")
    mode         = data.get("mode", "detailed").strip().lower()

    if mode not in ["simple", "detailed", "exam", "bullet"]:
        mode = "detailed"

    if not pdf_name or not question:
        return jsonify({
            "answer": "Missing book name or question.",
            "source_page": None, "matched_section": None,
            "confidence": "low", "followups": []
        }), 400

    if not is_query_meaningful(question):
        return jsonify({
            "answer": "I couldn't find a relevant academic question in this book. Try asking about a topic or concept from the subject.",
            "source_page": None, "matched_section": None,
            "confidence": "low", "intent": "invalid", "mode": mode,
            "followups": [
                "What is this chapter about?",
                "Give important points from this page",
                "Explain the current topic",
            ]
        })

    pdf_row      = fetch_pdf_by_name(pdf_name)
    file_path    = pdf_row["file_path"] if pdf_row else None
    summary_path = mirror_path(SUMMARY_FOLDER, file_path, pdf_name)
    flat_path    = os.path.join(SUMMARY_FOLDER, f"{pdf_name}.json")
    if not os.path.exists(summary_path) and os.path.exists(flat_path):
        summary_path = flat_path

    if not os.path.exists(summary_path):
        return jsonify({
            "answer": "Summary file not found for this book.",
            "source_page": None, "matched_section": None,
            "confidence": "low", "followups": []
        }), 404

    with open(summary_path, encoding="utf-8") as f:
        summary_data = json.load(f)

    sections = summary_data.get("sections", {})
    intent   = detect_intent(question)

    best_section = None
    best_score   = -1
    for _, section in sections.items():
        score = score_match(question, section, current_page=current_page)
        if score > best_score:
            best_score   = score
            best_section = section

    page_fallback = search_page_texts(question, pdf_name, current_page)
    page_score    = page_fallback["score"] if page_fallback else 0

    if best_score < 18 and page_score < 18:
        return jsonify({
            "answer": "I couldn't find a clearly relevant answer for that in this book. Try asking using a topic name, definition, process, formula, or exam-style question.",
            "source_page": None, "matched_section": None,
            "confidence": "low", "intent": intent, "mode": mode,
            "followups": [
                "What is this chapter about?",
                "Give important points from this page",
                "Explain the current topic",
                "Write a short note on this topic",
            ]
        })

    if page_fallback and page_fallback["score"] > best_score and page_fallback["score"] >= 18:
        answer = build_answer_from_page_text(question, page_fallback["text"], mode=mode)
        return jsonify({
            "answer":          answer,
            "source_page":     page_fallback["page"],
            "matched_section": "Matched Page Content",
            "confidence":      confidence_label(page_fallback["score"]),
            "intent":          intent,
            "mode":            mode,
            "followups": [
                "Explain this simply",
                "Give important points",
                "Write a short note on this topic",
            ]
        })

    if not best_section:
        return jsonify({
            "answer": "I couldn't find a relevant answer in this book.",
            "source_page": None, "matched_section": None,
            "confidence": "low", "intent": intent, "mode": mode,
            "followups": [
                "What is this chapter about?",
                "Give important points from this page",
            ]
        })

    answer    = build_answer_from_section(question, best_section, mode=mode)
    followups = generate_followups(best_section, intent)

    return jsonify({
        "answer":          answer,
        "source_page":     best_section.get("start_page"),
        "matched_section": best_section.get("title", "Matched Section"),
        "confidence":      confidence_label(best_score),
        "intent":          intent,
        "mode":            mode,
        "followups":       followups,
    })
