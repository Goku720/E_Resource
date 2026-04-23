import re

STOPWORDS = {
    "the", "is", "are", "was", "were", "and", "or", "of", "to", "in", "on",
    "for", "with", "as", "by", "an", "a", "from", "that", "this", "these",
    "those", "be", "it", "at", "which", "can", "has", "have", "had", "will",
    "shall", "may", "might", "would", "should", "into", "about", "than",
    "their", "there", "them", "its", "also", "not", "such", "using", "used"
}

BAD_WORDS = {
    "page", "unit", "chapter", "lesson", "introduction", "summary",
    "figure", "table", "example", "exercise", "question", "answer",
    "www", "http", "https", "com", "pdf", "university", "college"
}

def clean_text(text):
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'[^A-Za-z0-9\s\-]', ' ', text)
    return text.strip()

def extract_heading_like_lines(text):
    lines = text.split("\n")
    candidates = []

    for line in lines:
        line = line.strip()
        if not line:
            continue

        words = line.split()
        if 2 <= len(words) <= 8:
            if line.isupper() or line.istitle():
                candidates.append(line)

    return candidates

def extract_noun_phrases_simple(text):
    text = clean_text(text)
    words = text.split()

    phrases = []
    current = []

    for w in words:
        wl = w.lower()

        if wl in STOPWORDS or wl in BAD_WORDS or len(wl) < 3:
            if len(current) >= 2:
                phrases.append(" ".join(current))
            current = []
        else:
            current.append(w)

        if len(current) >= 4:
            phrases.append(" ".join(current))
            current = []

    if len(current) >= 2:
        phrases.append(" ".join(current))

    return phrases

def score_topic(topic):
    words = topic.split()
    score = 0

    if 2 <= len(words) <= 5:
        score += 3

    if topic.isupper() or topic.istitle():
        score += 2

    if not any(w.lower() in BAD_WORDS for w in words):
        score += 2

    if all(len(w) > 2 for w in words):
        score += 1

    return score

def extract_topics(text, max_topics=3):
    if not text or len(text.strip()) < 20:
        return []

    candidates = []

    # 1. heading-like candidates
    heading_lines = extract_heading_like_lines(text)
    candidates.extend(heading_lines)

    # 2. phrase candidates
    phrase_lines = extract_noun_phrases_simple(text[:1500])
    candidates.extend(phrase_lines)

    # clean + deduplicate
    cleaned = []
    seen = set()

    for c in candidates:
        c = clean_text(c)
        c = " ".join(c.split())

        if not c or len(c.split()) < 2:
            continue

        if c.lower() in seen:
            continue

        seen.add(c.lower())
        cleaned.append(c)

    # rank
    ranked = sorted(cleaned, key=score_topic, reverse=True)

    # final cleanup
    final_topics = []
    for topic in ranked:
        if len(final_topics) >= max_topics:
            break

        if len(topic) > 50:
            continue

        if any(bad in topic.lower() for bad in BAD_WORDS):
            continue

        final_topics.append(topic)

    return final_topics