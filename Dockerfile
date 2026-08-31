FROM python:3.11-slim

WORKDIR /app

# System dependencies:
# - tesseract-ocr: the OCR engine pytesseract calls into
# - libgl1: needed by Pillow/PyMuPDF for image handling
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    libgl1 \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first so Docker caches this layer —
# dependencies only reinstall when Requirement.txt actually changes
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt --extra-index-url https://download.pytorch.org/whl/cpu

# Now copy the rest of the app code
COPY . .

EXPOSE 5000

CMD ["python", "app.py"]