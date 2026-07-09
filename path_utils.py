# path_utils.py
# Shared helper for computing "mirrored" JSON paths that follow the same
# subfolder structure as the original uploaded PDF.
#
# Example:
#   pdf_path = uploads/BCA/Semester_1/Intro/Block1.pdf
#   base_folder = "summaries"
#   -> summaries/BCA/Semester_1/Intro/Block1.json
#
# Falls back to a flat "base_folder/pdf_name.json" if pdf_path is missing,
# invalid, or escapes outside upload_folder.

import os
from config import UPLOAD_FOLDER


def mirror_path(base_folder, pdf_path, pdf_name, upload_folder=UPLOAD_FOLDER):
    if pdf_path:
        try:
            rel = os.path.relpath(pdf_path, upload_folder)
            if not rel.startswith(".."):
                rel_json = os.path.splitext(rel)[0] + ".json"
                return os.path.join(base_folder, rel_json)
        except ValueError:
            pass
    return os.path.join(base_folder, f"{pdf_name}.json")