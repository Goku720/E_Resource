# E_Resource

An AI-powered e-resource platform for KKHSOU (Krishna Kanta Handiqui State Open University), built to give students searchable, summarized access to their course PDFs — with OCR, AI summarization, and a Q&A interface, running as an async background pipeline behind a Flask app.

Built during a 6-month industrial internship at the KKHSOU IT Cell.

## What it does

- Students log in (via KKHSOU's external API) and browse their enrolled programme's papers by semester
- Admins upload course PDFs, tagged to a specific paper/block
- Uploaded PDFs are processed asynchronously in the background:
  - OCR (Tesseract, multi-language) for scanned pages; skipped for pages with a native text layer
  - AI summarization via DistilBART (English) and AI4Bharat's MultiIndicSentenceSummarizationSS (regional Indian languages)
  - Junk-page filtering
- An "Ask This Book" feature answers questions about a PDF's content using a rule-based pipeline (intent detection + weighted keyword scoring + page-level fallback)
- A flipbook-style PDF viewer for reading
- Guest access with configurable page limits

## Stack

| Layer | Tech |
|---|---|
| Web framework | Flask |
| Async task queue | Celery + Redis |
| Database | MySQL (PyMySQL) |
| OCR | Tesseract |
| Summarization | Hugging Face Transformers — DistilBART, AI4Bharat MultiIndicSentenceSummarizationSS |
| Containerization | Docker + Docker Compose |
| Deployment | AWS EC2 (Ubuntu 22.04) |

## Architecture

```
Browser → Flask (web) → MySQL (programme/paper/student data)
                      → Redis (task queue)
                      → Celery (worker) → Tesseract OCR → Transformers summarization
```

`web` and `worker` share the same Docker image, started with different commands — Flask handles requests, Celery handles the actual PDF processing pipeline in the background, so uploads don't block the UI.

## Running locally with Docker

**Requirements:** Docker Desktop (or Docker Engine + Compose on Linux)

```bash
git clone https://github.com/Goku720/E_Resource.git
cd E_Resource
cp .env.example .env   # fill in real values — see below
docker compose build
docker compose up -d
```

Seed test data:
```bash
docker compose exec web python seed_students.py
```

Then visit `http://localhost:5000/login`.

### Environment variables (`.env`)

| Variable | Description |
|---|---|
| `MYSQL_HOST` / `MYSQL_PORT` / `MYSQL_USER` / `MYSQL_PASSWORD` / `MYSQL_DB` | MySQL connection |
| `REDIS_URL` | Redis connection string, used by Celery as broker + result backend |
| `KKHSOU_API_BASE` / `KKHSOU_API_KEY` | KKHSOU's external student API (not needed if `USE_FAKE_LOGIN=True`) |
| `SECRET_KEY` | Flask session signing key |

Set `USE_FAKE_LOGIN=True` in `config.py` to test locally without access to the real KKHSOU API — this checks credentials against locally seeded student records instead.

## Deployment

Deployed on an AWS EC2 (t2.micro, Ubuntu 22.04) free-tier instance, containerized with the same `docker-compose.yml` used for local development. Given the instance's 1GB RAM, a swap file is required for the summarization model to load without triggering an OOM kill.

## Known limitations

- **Memory-constrained inference**: running transformer models locally on a 1GB free-tier instance is slow (relies heavily on swap). A planned improvement is offloading summarization to a hosted inference API (e.g. Hugging Face Inference API) instead of loading model weights on the app server itself.
- Celery worker concurrency is capped by available CPU — single-core free-tier instances process uploads sequentially rather than in parallel.

## Project history

Started as a basic Flask app with SQLite and a turn.js flipbook viewer. Evolved through: TTS accessibility features, YouTube video recommendations, role-based authentication, a migration from SQLite to MySQL, and a full Dockerized deployment to AWS.
