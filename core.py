"""Core retrieval logic: parse a PDF, chunk it, embed it, search it, answer from it."""

import io
import os

import numpy as np
import fitz  # PyMuPDF
from groq import Groq
from fastembed import TextEmbedding

# ---------------- settings ----------------
EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
LLM_MODEL = "openai/gpt-oss-120b"     # Groq deprecates models periodically
CHUNK_SIZE = 160                      # words; stays inside the model's 256-token limit
OVERLAP = 40
MIN_WORDS = 25
TOP_K = 3
MIN_SCORE = 0.28                      # below this, refuse instead of guessing
MAX_PAGES = 400

SYSTEM_PROMPT = """You answer questions about a vehicle service manual using ONLY \
the excerpts given to you.

Rules:
- If the excerpts do not contain the answer, reply with exactly: NOT_IN_DOCS
- If the question asks about a different vehicle or model than the excerpts \
describe, reply with exactly: NOT_IN_DOCS
- Never invent a number, torque value, capacity, interval or limit.
- Quote figures exactly as written, including units.
- Cite sources as [page N] using plain square brackets only, never other bracket characters.
- Answer in at most three sentences unless a list is genuinely needed."""

_model = None


def get_model():
    """Load the embedding model once and reuse it.

    fastembed runs the same MiniLM weights through ONNX Runtime instead of
    PyTorch. Same vectors, but ~100 MB of dependencies instead of ~2 GB, which
    is what lets this run on a 512 MB free tier.
    """
    global _model
    if _model is None:
        _model = TextEmbedding(EMBED_MODEL)
    return _model


def embed(texts):
    """Embed a list of strings and L2-normalise, so a dot product later gives
    cosine similarity directly."""
    vectors = np.array(list(get_model().embed(texts)), dtype="float32")
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return vectors / norms


def parse_pdf(file_bytes, filename):
    """PDF bytes -> list of chunks with page numbers."""
    chunks = []
    step = CHUNK_SIZE - OVERLAP
    empty_pages = 0

    with fitz.open(stream=file_bytes, filetype="pdf") as pdf:
        page_count = min(pdf.page_count, MAX_PAGES)
        for page_no in range(1, page_count + 1):
            page = pdf[page_no - 1]
            # this manual is a trilingual print layout where each language sits
            # outside the crop box; widening it recovers the clipped text
            page.set_cropbox(page.mediabox)
            text = page.get_text() or ""
            words = text.split()
            if len(words) < MIN_WORDS:
                empty_pages += 1
                continue
            # Contents and index pages are dense lists of topic names with no
            # answers in them. They match almost every question and crowd out
            # the page that actually holds the answer, so drop them.
            dots = text.count("..")
            if dots > 8:
                empty_pages += 1
                continue
            for i in range(0, len(words), step):
                piece = words[i:i + CHUNK_SIZE]
                if len(piece) >= MIN_WORDS:
                    chunks.append({
                        "text": " ".join(piece),
                        "page": page_no,
                        "doc": filename,
                    })

    return chunks, page_count, empty_pages


def build_index(chunks):
    """Embed every chunk in the document."""
    return embed([c["text"] for c in chunks])


def search(question, chunks, vectors, top_k=TOP_K):
    q = embed([question])[0]
    scores = vectors @ q
    top = np.argsort(-scores)[:top_k]
    return [
        {
            "text": chunks[i]["text"],
            "page": chunks[i]["page"],
            "doc": chunks[i]["doc"],
            "score": round(float(scores[i]), 3),
        }
        for i in top
    ]


def ask_llm(question, hits):
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        raise RuntimeError("GROQ_API_KEY is not set on the server.")

    context = "\n\n---\n\n".join(
        f"[page {h['page']}]\n{h['text']}" for h in hits
    )
    resp = Groq(api_key=key).chat.completions.create(
        model=LLM_MODEL,
        temperature=0.1,
        max_tokens=600,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",
             "content": f"Excerpts:\n\n{context}\n\nQuestion: {question}"},
        ],
    )
    return resp.choices[0].message.content.strip()


def answer(question, chunks, vectors):
    """Two independent guards decide whether to answer.

    1. Similarity floor  - nothing relevant was retrieved at all.
    2. Prompt constraint - retrieval succeeded but the content is about
       something else (a different vehicle, say). Only the model can see this.
    """
    hits = search(question, chunks, vectors)
    top_score = hits[0]["score"] if hits else 0.0

    if top_score < MIN_SCORE:
        return {
            "answer": "That isn't covered in this manual.",
            "refused": True,
            "refused_by": "similarity floor",
            "top_score": top_score,
            "threshold": MIN_SCORE,
            "sources": hits,
        }

    text = ask_llm(question, hits)

    if "NOT_IN_DOCS" in text:
        return {
            "answer": "The manual covers this topic, but not for what you asked about.",
            "refused": True,
            "refused_by": "content mismatch",
            "top_score": top_score,
            "threshold": MIN_SCORE,
            "sources": hits,
        }

    return {
        "answer": text,
        "refused": False,
        "refused_by": None,
        "top_score": top_score,
        "threshold": MIN_SCORE,
        "sources": hits,
    }
