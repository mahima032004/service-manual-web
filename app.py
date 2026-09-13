"""Flask server: upload a manual, then ask questions about it."""

import traceback
import uuid

from flask import Flask, jsonify, render_template, request

import core

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 30 * 1024 * 1024  # 30 MB

# doc_id -> {chunks, vectors, filename, pages}
# In memory: restarting the server clears uploads. Fine for a single-user demo.
DOCS = {}
MAX_DOCS = 8


@app.route("/")
def index():
    return render_template("index.html")


@app.post("/upload")
def upload():
    file = request.files.get("file")
    if not file or not file.filename:
        return jsonify(error="Choose a PDF to upload."), 400
    if not file.filename.lower().endswith(".pdf"):
        return jsonify(error="That file isn't a PDF."), 400

    try:
        data = file.read()
        chunks, page_count, empty_pages = core.parse_pdf(data, file.filename)
    except Exception:
        traceback.print_exc()
        return jsonify(error="That PDF couldn't be read. It may be corrupted."), 400

    if not chunks:
        return jsonify(
            error="No text found in this PDF. It's probably a scan of printed "
                  "pages, which needs OCR before it can be searched."
        ), 400

    try:
        vectors = core.build_index(chunks)
    except Exception:
        traceback.print_exc()
        return jsonify(error="Indexing failed on the server."), 500

    # keep memory bounded
    if len(DOCS) >= MAX_DOCS:
        DOCS.pop(next(iter(DOCS)))

    doc_id = uuid.uuid4().hex[:12]
    DOCS[doc_id] = {
        "chunks": chunks,
        "vectors": vectors,
        "filename": file.filename,
        "pages": page_count,
    }

    return jsonify(
        doc_id=doc_id,
        filename=file.filename,
        pages=page_count,
        chunks=len(chunks),
        skipped_pages=empty_pages,
    )


@app.post("/ask")
def ask():
    payload = request.get_json(silent=True) or {}
    doc_id = payload.get("doc_id")
    question = (payload.get("question") or "").strip()

    if not question:
        return jsonify(error="Type a question first."), 400

    doc = DOCS.get(doc_id)
    if not doc:
        return jsonify(
            error="This manual is no longer loaded. Upload it again."
        ), 404

    try:
        result = core.answer(question, doc["chunks"], doc["vectors"])
    except RuntimeError as e:
        return jsonify(error=str(e)), 500
    except Exception:
        traceback.print_exc()
        return jsonify(error="The answer service failed. Try again."), 500

    return jsonify(result)


@app.get("/health")
def health():
    return jsonify(status="ok", docs_loaded=len(DOCS))


if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 7860))
    app.run(host="0.0.0.0", port=port)
