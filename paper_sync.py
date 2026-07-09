# paper_sync.py
# For bachelor programmes:
#   1. Call selected-papers to find which minor the student chose
#   2. Call program-papers with (program_code, semester, minor) to get the
#      full structured paper list (common papers + minor papers together)
# For master/PG programmes:
#   - Call program-papers with (program_code, semester) — no minor needed
#   - Fall back to selected-papers if program-papers fails
# ─────────────────────────────────────────────────────────────

import requests
from config import KKHSOU_API_BASE, KKHSOU_API_KEY
from database import get_db

BACHELOR_PREFIXES = {"BA", "BSC", "BCOM", "BCA", "BSW", "BPS", "BBA", "BHM", "BARC", "BLIS",
                     "BAA", "BEG", "BAE", "BED", "BAH", "BPH", "BSO"}

# All available minor subjects — same pool for all degree programmes
KKHSOU_MINORS = [
    "Assamese",
    "Economics",
    "English",
    "History",
    "Philosophy",
    "Political Science",
    "Sanskrit",
    "Social Work",
    "Sociology",
    "Education",
    "BBA",
    "Commerce",
    "BCA",
    "Journalism and Mass Communication",
    "Mathematics",
]

def is_bachelor(prog_code):
    code = (prog_code or "").upper().replace(".", "").replace(" ", "")
    return any(code.startswith(b.replace(".", "")) for b in BACHELOR_PREFIXES)


def map_paper_type(paper):
    group_code = (paper.get("group_code") or "").upper().strip()
    group_type = (paper.get("group_type") or "").lower()

    # Direct group_code mapping first — most reliable
    gc_map = {
        "MAJOR": "DSC",
        "MINOR": "DSE",
        "IDC":   "GE",
        "AEC":   "AEC",
        "VAC":   "VAC",
        "SEC":   "SEC",
        "DSC":   "DSC",
        "DSE":   "DSE",
        "GE":    "GE",
        "OE":    "GE",
        "CORE":  "DSC",
        "ELECTIVE": "DSE",
    }
    if group_code in gc_map:
        return gc_map[group_code]

    # Fallback to group_type string
    if "field work"    in group_type: return "FW"
    if "dissertation"  in group_type: return "FW"
    if "project"       in group_type: return "FW"
    if "ability"       in group_type: return "AEC"
    if "value"         in group_type: return "VAC"
    if "skill"         in group_type: return "SEC"
    if "generic"       in group_type: return "GE"
    if "inter-disciplinary" in group_type: return "GE"
    if "elective"      in group_type: return "DSE"
    if "specific core" in group_type: return "DSC"
    if "core"          in group_type: return "DSC"
    if "major"         in group_type: return "DSC"
    if "minor"         in group_type: return "DSE"

    return "DSC"
# Paper types that are always common — never minor-specific
_COMMON_PAPER_TYPES = {"DSC", "AEC", "VAC", "SEC", "FW", "GE"}


def _paper_minor_from_group_name(group_name, prog_code):
    """
    Returns the minor subject name if group_name looks like a real subject,
    or None if it's a generic label / the programme name itself.
    """
    generic_labels = {
        "core", "elective", "optional", "compulsory", "common",
        "ability enhancement", "value added", "skill enhancement",
        "generic elective", "field work", "project", "dissertation",
        "aecc", "vac", "sec", "ge", "dsc", "dse",
    }
    if not group_name:
        return None

    prog_upper = (prog_code or "").upper().replace(".", "").replace(" ", "")
    gn_upper   = group_name.upper().replace(".", "").replace(" ", "")

    if gn_upper == prog_upper:
        return None
    if group_name.lower() in generic_labels:
        return None

    # Skip if group_name is the programme's own discipline subject
    # e.g. BPS → "Political Science", MAS → "Assamese", etc.
    prog_subject_map = {
        "BPS":  "political science",
        "MAS":  "assamese",
        "MHI":  "history",
        "MEC":  "economics",
        "MSO":  "sociology",
        "MBA":  "mba",
        "MCA":  "computer application",
        "BSC":  "science",
        "BCOM": "commerce",
    }
    own_subject = prog_subject_map.get(prog_upper, "")
    if own_subject and group_name.lower().strip() == own_subject:
        return None

    return group_name


def extract_minor_from_selected(api_papers, prog_code):
    if not is_bachelor(prog_code):
        return None

    for p in api_papers:
        group_code = (p.get("group_code") or "").upper().strip()
        
        # Direct match — API explicitly marks minor papers
        if group_code == "MINOR":
            paper_name = (p.get("paper_name") or "").strip()
            # Extract subject from paper name if possible,
            # otherwise use group_name as the minor label
            group_name = (p.get("group_name") or "").strip()
            minor = paper_name if paper_name else group_name
            if minor and not minor.lower().endswith("(minor)"):
                minor = f"{minor} (Minor)"
            print(f"[paper_sync] Minor detected from group_code=MINOR: {minor!r}")
            return minor

    # Fallback — old logic for other API formats
    for p in api_papers:
        group_name = (p.get("group_name") or "").strip()
        group_code = (p.get("group_code") or "").lower().strip()
        if group_code in ("core", "dsc", "aecc", "aec", "vac", "sec", "major", "idc"):
            continue
        m = _paper_minor_from_group_name(group_name, prog_code)
        if m:
            if not m.lower().endswith("(minor)"):
                m = f"{m} (Minor)"
            return m

    return None
# ─────────────────────────────────────────────────────────────
# API CALLS
# ─────────────────────────────────────────────────────────────

def _headers(access_token=None):
    return {
        "Content-Type": "application/json",
        "X-API-KEY":    KKHSOU_API_KEY,
    }


def fetch_selected_papers_from_api(enrollment_no, semester, access_token=None):
    url  = f"{KKHSOU_API_BASE}/api/v1/student/selected-papers"
    body = {"enrollment_no": enrollment_no, "semester": semester}
    try:
        resp = requests.post(url, json=body, headers=_headers(access_token), timeout=10)
        print(f"[paper_sync] selected-papers HTTP {resp.status_code} "
              f"enrollment={enrollment_no} sem={semester}")
        data = resp.json()
        print(f"[paper_sync] Response: {data}")
        if data.get("status") == "success":
            papers = data.get("data", {}).get("papers", [])
            print(f"[paper_sync] Got {len(papers)} selected papers")
            return papers
        print(f"[paper_sync] API error: {data.get('message', 'unknown')}")
    except Exception as e:
        print(f"[paper_sync] selected-papers failed for enrollment={enrollment_no}: {e}")
    return []


def fetch_program_papers_from_api(prog_code, semester, access_token=None, minor=None):
    """
    POST /api/v1/student/program-papers
    Returns flat list of paper dicts for the given programme+semester.
    Pass minor for bachelor programmes (required by the API for DEGREE group).
    """
    url  = f"{KKHSOU_API_BASE}/api/v1/student/program-papers"
    body = {"program_code": prog_code, "semester": semester}
    if minor:
        body["minor"] = minor

    try:
        resp = requests.post(url, json=body, headers=_headers(access_token), timeout=10)
        print(f"[paper_sync] program-papers HTTP {resp.status_code} "
              f"prog={prog_code} sem={semester} minor={minor}")
        data = resp.json()
        if data.get("status") == "success":
            semesters = data.get("data", {}).get("semesters", [])
            for sem_block in semesters:
                if sem_block.get("semester") == semester:
                    papers = sem_block.get("papers", [])
                    print(f"[paper_sync] Got {len(papers)} program papers")
                    return papers
            # Fallback: flatten all semester blocks
            all_papers = []
            for sem_block in semesters:
                all_papers.extend(sem_block.get("papers", []))
            print(f"[paper_sync] Got {len(all_papers)} program papers (all sems flattened)")
            return all_papers
        print(f"[paper_sync] program-papers API error: {data.get('message', 'unknown')}")
    except Exception as e:
        print(f"[paper_sync] program-papers failed for prog={prog_code}: {e}")
    return []


# ─────────────────────────────────────────────────────────────
# DB
# ─────────────────────────────────────────────────────────────

def semester_has_papers(programme_id, semester):
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) as cnt FROM papers WHERE programme_id=%s AND semester=%s",
            (programme_id, semester)
        )
        row = cur.fetchone()
    conn.close()
    return row["cnt"] > 0


def store_papers(programme_id, semester, api_papers, prog_code, minor=None):
    if not api_papers:
        return 0

    conn  = get_db()
    count = 0

    with conn.cursor() as cur:
        for p in api_papers:
            paper_name = (p.get("paper_name") or "").strip()
            if not paper_name:
                continue

            paper_type = map_paper_type(p)
            group_code_upper = (p.get("group_code") or "").upper().strip()  # ← define it here

            if is_bachelor(prog_code):
                if group_code_upper in ("MAJOR", "AEC", "VAC", "SEC", "FW", "IDC"):
                    paper_minor = None
                elif group_code_upper == "MINOR":
                    paper_minor = (p.get("group_name") or "").strip() or None
                else:
                    paper_minor = None
            else:
                paper_minor = None

            # Skip duplicate
            cur.execute("""
                SELECT id FROM papers
                WHERE programme_id=%s AND semester=%s AND paper_name=%s
                AND (minor=%s OR (minor IS NULL AND %s IS NULL))
            """, (programme_id, semester, paper_name, paper_minor, paper_minor))
            if cur.fetchone():
                print(f"[paper_sync] Skipping duplicate: {paper_name} (minor={paper_minor})")
                continue

            cur.execute("""
                INSERT INTO papers (programme_id, semester, paper_type, paper_name, minor)
                VALUES (%s, %s, %s, %s, %s)
            """, (programme_id, semester, paper_type, paper_name, paper_minor))
            count += 1
            minor_label = f" [minor: {paper_minor}]" if paper_minor else ""
            print(f"[paper_sync] Inserted: [{paper_type}] {paper_name}{minor_label}")

    conn.commit()
    conn.close()
    print(f"[paper_sync] ✅ Stored {count} new papers for "
          f"programme_id={programme_id} sem={semester}")
    return count


# ─────────────────────────────────────────────────────────────
# MAIN ENTRY POINT
# ─────────────────────────────────────────────────────────────

def sync_papers_for_student(programme_id, prog_code, semester,
                             enrollment_no, access_token=None):
    if semester_has_papers(programme_id, semester):
        print(f"[paper_sync] Papers already exist for "
              f"programme_id={programme_id} sem={semester}, skipping.")
        return

    print(f"[paper_sync] Syncing — prog={prog_code} sem={semester}")

    # Just call program-papers directly — works for both bachelor and masters
    api_papers = fetch_program_papers_from_api(prog_code, semester, access_token)

    if not api_papers:
        print(f"[paper_sync] program-papers empty; falling back to selected-papers")
        api_papers = fetch_selected_papers_from_api(enrollment_no, semester, access_token)

    if api_papers:
        store_papers(programme_id, semester, api_papers, prog_code)
    else:
        print(f"[paper_sync] ⚠ No papers found for enrollment={enrollment_no} sem={semester}")