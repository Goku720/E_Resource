# seed.py
# Populates the database with data.
# ─────────────────────────────────────────────────────────────
# Run: python seed.py

import os
from database import get_db, init_db

UPLOAD_FOLDER = "uploads"

# ═══════════════════════════════════════════════════════════════
# DATA  ← swap these with real API calls later
# ═══════════════════════════════════════════════════════════════

PROGRAMMES = [
    {"id": 1, "code": "MAS",  "name": "Master of Arts in Assamese"},
    {"id": 2, "code": "BCA",  "name": "Bachelor of Computer Applications"},
    {"id": 3, "code": "BCOM", "name": "Bachelor of Commerce"},
    {"id": 4, "code": "MEG",  "name": "Master of Arts in English"},
    {"id": 5, "code": "BSW",  "name": "Bachelor of Social Work"},
]

PAPERS = [
    # ── MAS Semester 1 ──────────────────────────────────────
    {"id": 1,  "programme_id": 1, "semester": 1, "paper_type": "DSC", "paper_name": "History of Assamese Literature (Beginning to Medieval Period)"},
    {"id": 2,  "programme_id": 1, "semester": 1, "paper_type": "DSC", "paper_name": "History of Assamese Literature (Arunodoi Era to Post Ramdhenu Era)"},
    {"id": 3,  "programme_id": 1, "semester": 1, "paper_type": "DSC", "paper_name": "The Assamese Language: Introduction and Development"},
    {"id": 4,  "programme_id": 1, "semester": 1, "paper_type": "DSE", "paper_name": "Western Influence on Assamese Literature"},
    {"id": 5,  "programme_id": 1, "semester": 1, "paper_type": "AEC", "paper_name": "English for Media Studies"},
    {"id": 6,  "programme_id": 1, "semester": 1, "paper_type": "VAC", "paper_name": "English Communication Skills"},
    # ── MAS Semester 2 ──────────────────────────────────────
    {"id": 7,  "programme_id": 1, "semester": 2, "paper_type": "DSC", "paper_name": "Assamese Poetry: Classical Forms and Styles"},
    {"id": 8,  "programme_id": 1, "semester": 2, "paper_type": "DSC", "paper_name": "Modern Assamese Prose and Fiction"},
    {"id": 9,  "programme_id": 1, "semester": 2, "paper_type": "DSE", "paper_name": "Folk Literature of Assam"},
    {"id": 10, "programme_id": 1, "semester": 2, "paper_type": "VAC", "paper_name": "Environmental Studies"},
    # ── BCA Semester 1 ──────────────────────────────────────
    {"id": 11, "programme_id": 2, "semester": 1, "paper_type": "DSC", "paper_name": "Introduction to Programming using C"},
    {"id": 12, "programme_id": 2, "semester": 1, "paper_type": "DSC", "paper_name": "Computer Fundamentals and Office Automation"},
    {"id": 13, "programme_id": 2, "semester": 1, "paper_type": "DSC", "paper_name": "Mathematics for Computing"},
    {"id": 14, "programme_id": 2, "semester": 1, "paper_type": "AEC", "paper_name": "English Communication"},
    {"id": 15, "programme_id": 2, "semester": 1, "paper_type": "VAC", "paper_name": "Environmental Studies"},
    # ── BCA Semester 2 ──────────────────────────────────────
    {"id": 16, "programme_id": 2, "semester": 2, "paper_type": "DSC", "paper_name": "Data Structures using C"},
    {"id": 17, "programme_id": 2, "semester": 2, "paper_type": "DSC", "paper_name": "Database Management Systems"},
    {"id": 18, "programme_id": 2, "semester": 2, "paper_type": "DSE", "paper_name": "Web Technology"},
    {"id": 19, "programme_id": 2, "semester": 2, "paper_type": "SEC", "paper_name": "Python Programming Lab"},
    # ── BCOM Semester 1 ─────────────────────────────────────
    {"id": 20, "programme_id": 3, "semester": 1, "paper_type": "DSC", "paper_name": "Financial Accounting"},
    {"id": 21, "programme_id": 3, "semester": 1, "paper_type": "DSC", "paper_name": "Business Organisation and Management"},
    {"id": 22, "programme_id": 3, "semester": 1, "paper_type": "AEC", "paper_name": "Business Communication"},
    {"id": 23, "programme_id": 3, "semester": 1, "paper_type": "VAC", "paper_name": "Environmental Studies"},
    # ── MEG Semester 1 ──────────────────────────────────────
    {"id": 24, "programme_id": 4, "semester": 1, "paper_type": "DSC", "paper_name": "British Poetry and Drama: 14th to 17th Centuries"},
    {"id": 25, "programme_id": 4, "semester": 1, "paper_type": "DSC", "paper_name": "European Classical Literature"},
    {"id": 26, "programme_id": 4, "semester": 1, "paper_type": "DSE", "paper_name": "Indian Writing in English"},
    {"id": 27, "programme_id": 4, "semester": 1, "paper_type": "AEC", "paper_name": "Academic Writing and Research Methods"},
]

PDFS = [
    {"paper_id": 1,  "title": "Block 1 — Early Assamese Literature",           "pdf_name": "MAS_S1_P1_Block1"},
    {"paper_id": 1,  "title": "Block 2 — Medieval Period Overview",             "pdf_name": "MAS_S1_P1_Block2"},
    {"paper_id": 1,  "title": "Block 3 — Regional Variations and Dialects",    "pdf_name": "MAS_S1_P1_Block3"},
    {"paper_id": 2,  "title": "Block 1 — The Arunodoi Era",                    "pdf_name": "MAS_S1_P2_Block1"},
    {"paper_id": 2,  "title": "Block 2 — Post Ramdhenu Era Literature",        "pdf_name": "MAS_S1_P2_Block2"},
    {"paper_id": 3,  "title": "Block 1 — Introduction to Assamese Language",   "pdf_name": "MAS_S1_P3_Block1"},
    {"paper_id": 3,  "title": "Block 2 — Language Development and Scripts",    "pdf_name": "MAS_S1_P3_Block2"},
    {"paper_id": 4,  "title": "Block 1 — Western Literary Influences",         "pdf_name": "MAS_S1_P4_Block1"},
    {"paper_id": 5,  "title": "Block 1 — Media Writing Fundamentals",          "pdf_name": "MAS_S1_P5_Block1"},
    {"paper_id": 6,  "title": "Block 1 — English Communication Skills",        "pdf_name": "MAS_S1_P6_Block1"},
    {"paper_id": 7,  "title": "Block 1 — Classical Assamese Poetry",           "pdf_name": "MAS_S2_P7_Block1"},
    {"paper_id": 7,  "title": "Block 2 — Poetic Forms and Analysis",           "pdf_name": "MAS_S2_P7_Block2"},
    {"paper_id": 8,  "title": "Block 1 — Modern Assamese Prose",               "pdf_name": "MAS_S2_P8_Block1"},
    {"paper_id": 8,  "title": "Block 2 — Contemporary Assamese Fiction",       "pdf_name": "MAS_S2_P8_Block2"},
    {"paper_id": 9,  "title": "Block 1 — Folk Literature Overview",            "pdf_name": "MAS_S2_P9_Block1"},
    {"paper_id": 9,  "title": "Block 2 — Oral Traditions of Assam",            "pdf_name": "MAS_S2_P9_Block2"},
    {"paper_id": 10, "title": "Block 1 — Environmental Studies",               "pdf_name": "MAS_S2_P10_Block1"},
    {"paper_id": 11, "title": "Block 1 — Introduction to C Programming",       "pdf_name": "BCA_S1_P11_Block1"},
    {"paper_id": 11, "title": "Block 2 — Control Structures and Loops",        "pdf_name": "BCA_S1_P11_Block2"},
    {"paper_id": 11, "title": "Block 3 — Functions and Arrays",                "pdf_name": "BCA_S1_P11_Block3"},
    {"paper_id": 11, "title": "Block 4 — Pointers, Structures and Files",      "pdf_name": "BCA_S1_P11_Block4"},
    {"paper_id": 12, "title": "Block 1 — Computer Fundamentals",               "pdf_name": "BCA_S1_P12_Block1"},
    {"paper_id": 12, "title": "Block 2 — MS Office Suite",                     "pdf_name": "BCA_S1_P12_Block2"},
    {"paper_id": 13, "title": "Block 1 — Discrete Mathematics",                "pdf_name": "BCA_S1_P13_Block1"},
    {"paper_id": 13, "title": "Block 2 — Calculus and Linear Algebra",         "pdf_name": "BCA_S1_P13_Block2"},
    {"paper_id": 14, "title": "Block 1 — English Communication",               "pdf_name": "BCA_S1_P14_Block1"},
    {"paper_id": 15, "title": "Block 1 — Environmental Studies",               "pdf_name": "BCA_S1_P15_Block1"},
    {"paper_id": 16, "title": "Block 1 — Arrays, Stacks and Queues",           "pdf_name": "BCA_S2_P16_Block1"},
    {"paper_id": 16, "title": "Block 2 — Trees, Graphs and Sorting",           "pdf_name": "BCA_S2_P16_Block2"},
    {"paper_id": 17, "title": "Block 1 — Relational Model and SQL",            "pdf_name": "BCA_S2_P17_Block1"},
    {"paper_id": 17, "title": "Block 2 — Advanced DBMS Concepts",              "pdf_name": "BCA_S2_P17_Block2"},
    {"paper_id": 18, "title": "Block 1 — HTML, CSS and JavaScript",            "pdf_name": "BCA_S2_P18_Block1"},
    {"paper_id": 18, "title": "Block 2 — Server-Side Web Development",         "pdf_name": "BCA_S2_P18_Block2"},
    {"paper_id": 19, "title": "Block 1 — Python Programming Fundamentals",     "pdf_name": "BCA_S2_P19_Block1"},
    {"paper_id": 20, "title": "Block 1 — Accounting Basics and Journal",       "pdf_name": "BCOM_S1_P20_Block1"},
    {"paper_id": 20, "title": "Block 2 — Ledger, Trial Balance and Final A/C", "pdf_name": "BCOM_S1_P20_Block2"},
    {"paper_id": 21, "title": "Block 1 — Business Organisation",               "pdf_name": "BCOM_S1_P21_Block1"},
    {"paper_id": 21, "title": "Block 2 — Principles of Management",            "pdf_name": "BCOM_S1_P21_Block2"},
    {"paper_id": 22, "title": "Block 1 — Business Communication",              "pdf_name": "BCOM_S1_P22_Block1"},
    {"paper_id": 24, "title": "Block 1 — Chaucer and Medieval Poetry",         "pdf_name": "MEG_S1_P24_Block1"},
    {"paper_id": 24, "title": "Block 2 — Renaissance Drama and Poetry",        "pdf_name": "MEG_S1_P24_Block2"},
    {"paper_id": 25, "title": "Block 1 — Greek and Roman Literature",          "pdf_name": "MEG_S1_P25_Block1"},
    {"paper_id": 25, "title": "Block 2 — European Literary Traditions",        "pdf_name": "MEG_S1_P25_Block2"},
    {"paper_id": 26, "title": "Block 1 — Indian Writing in English",           "pdf_name": "MEG_S1_P26_Block1"},
    {"paper_id": 27, "title": "Block 1 — Academic Writing and Research",       "pdf_name": "MEG_S1_P27_Block1"},
]


# ═══════════════════════════════════════════════════════════════
# SEEDER
# ═══════════════════════════════════════════════════════════════

def seed():
    init_db()
    conn = get_db()

    with conn.cursor() as cur:
        # ── Programmes ──
        for p in PROGRAMMES:
            cur.execute(
                "INSERT IGNORE INTO programmes (id, code, name) VALUES (%s, %s, %s)",
                (p["id"], p["code"], p["name"])
            )
        print(f"  ✓ {len(PROGRAMMES)} programmes seeded")

        # ── Papers ──
        for p in PAPERS:
            cur.execute(
                """INSERT IGNORE INTO papers
                   (id, programme_id, semester, paper_type, paper_name)
                   VALUES (%s, %s, %s, %s, %s)""",
                (p["id"], p["programme_id"], p["semester"], p["paper_type"], p["paper_name"])
            )
        print(f"  ✓ {len(PAPERS)} papers seeded")

        # ── PDFs ──
        for pdf in PDFS:
            paper = next((p for p in PAPERS if p["id"] == pdf["paper_id"]), None)
            prog  = next((p for p in PROGRAMMES if p["id"] == (paper["programme_id"] if paper else 0)), None)

            if paper and prog:
                folder = os.path.join(
                    UPLOAD_FOLDER,
                    prog["code"],
                    f"Semester_{paper['semester']}",
                    paper["paper_name"].replace(" ", "_").replace("/", "-")[:50]
                )
                file_path = os.path.join(folder, f"{pdf['pdf_name']}.pdf")
            else:
                file_path = os.path.join(UPLOAD_FOLDER, f"{pdf['pdf_name']}.pdf")

            cur.execute(
                """INSERT IGNORE INTO pdfs (paper_id, title, pdf_name, file_path, status)
                   VALUES (%s, %s, %s, %s, 'pending')""",
                (pdf["paper_id"], pdf["title"], pdf["pdf_name"], file_path)
            )

        print(f"  ✓ {len(PDFS)} PDFs seeded (status: pending)")

    conn.commit()
    conn.close()
    print("\n✅ Seeding complete!")
    print("   Next step: upload real PDFs and update status to 'ready'")
    print("   Or use /admin/upload to upload PDFs manually\n")


if __name__ == "__main__":
    seed()
