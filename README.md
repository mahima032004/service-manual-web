# Service Manual Assistant

Upload a vehicle service manual and ask it questions in plain language. Every
answer cites the page it came from, and the assistant declines to answer when
the manual doesn't cover the question.


---

## The problem

A service manual is hundreds of pages of torque figures, service intervals and
troubleshooting tables. Finding one number means knowing which section to look
in. A general-purpose chatbot will answer the question confidently from its
training data, which is worse than useless when the figure has to be right for
a specific machine.

This system only answers from the document you give it, shows you the page, and
refuses when it can't find the answer.

## How it works

```
PDF upload
   → pdfplumber extracts text per page
   → split into overlapping 160-word chunks, each tagged with its page
   → all-MiniLM-L6-v2 embeds every chunk into a 384-dim vector

Question
   → embed the question
   → cosine similarity against every chunk, take the top 3
   → two independent checks decide whether to answer
   → LLM writes the answer from those excerpts only
```

### Two independent refusal mechanisms

This is the part that matters. A single guard isn't enough, and the reason is
easiest to see from the test results:

| Question | Top similarity | Outcome |
|---|---|---|
| What torque should the front axle nut be tightened to? | 0.51 | Answered, page 5 cited |
| How much petrol does it hold? | 0.37 | Answered — manual says "fuel tank capacity", never "petrol" |
| How do I replace the windscreen? | 0.27 | Refused by the similarity floor |
| What is the tyre pressure on a Yamaha R15? | **0.63** | Refused by the content check |

The last row is the interesting one. The question scored *higher* than any
answered question, because the manual genuinely does cover tyre pressure —
retrieval worked perfectly. But the pages describe a different vehicle, and
only the language model can recognise that. A similarity threshold alone would
have answered it, using the wrong machine's figures.

So:

1. **Similarity floor** (`MIN_SCORE = 0.28`) — rejects questions where nothing
   relevant was retrieved at all.
2. **Content check** — the model is instructed to return `NOT_IN_DOCS` when the
   excerpts are about a different subject than the question.

The interface shows the match strength and the cut-off line for every answer,
so the user can see how much confidence sits behind it.

## Retrieval evaluation

Measured against a hand-written set of 35 questions with known page numbers.

| chunk size | overlap | chunks | hit rate @1 | hit rate @3 |
|---|---|---|---|---|
| 80 | 20 | 31 | 77% | 97% |
| 160 | 0 | 13 | 80% | 97% |
| **160** | **40** | **18** | **80%** | **94%** |
| 300 | 80 | 12 | 83% | 94% |

The spread across all four configurations is two questions out of 35 — within
noise at this sample size. The honest conclusion is that **chunk size was not
the limiting factor** on this corpus, not that any one setting won.

One question failed under every configuration: *"What causes the motorcycle to
pull to one side?"* The answer is a terse table row — *misaligned rear wheel;
uneven tyre pressure; bent front fork* — with almost no vocabulary in common
with the question. Prose paragraphs elsewhere in the manual sound more like an
explanation and score higher. The limitation is document style, not chunk
boundary, and no chunking strategy fixes it. Hybrid keyword and vector search
would be the next thing to try.

## Stack

| Layer | Choice | Why |
|---|---|---|
| Text extraction | pdfplumber | Per-page extraction, which is what makes page citations possible |
| Embeddings | all-MiniLM-L6-v2 via ONNX Runtime (`fastembed`) | Same weights as the PyTorch version, but ~105 MB of dependencies instead of ~2 GB, which is what lets it run on a 512 MB free instance |
| Vector search | NumPy dot product | Exact search over a few thousand vectors takes milliseconds; an approximate index would add a dependency and a config surface for no measurable gain at this scale |
| Generation | Llama-class model via Groq | Fast inference, open weights, free tier |
| Backend | Flask | Two endpoints; a framework with more structure would be overhead |
| Frontend | Plain HTML, CSS and JavaScript | No build step |

Deliberately not used: LangChain or LlamaIndex. The pipeline is about 150 lines,
and writing it directly means retrieval failures are debuggable in my own code
rather than inside a framework abstraction.

**Chunk size note:** `all-MiniLM-L6-v2` truncates input at 256 tokens. Chunks are
160 *words*, which is roughly 230 tokens for technical text — deliberately inside
that limit. A larger chunk would have its tail silently dropped before embedding.

## Running it locally

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

export GROQ_API_KEY="gsk_..."      # Windows: $env:GROQ_API_KEY="gsk_..."
python app.py
```

Open http://localhost:7860

Get a free Groq API key at https://console.groq.com — no credit card needed.

## Deploying

Runs as a Docker container on Render's free tier. See DEPLOY.md.

## Limitations

- Uploaded documents live in server memory and are lost when the server
  restarts. Persisting them would need a database or object storage.
- Scanned PDFs return no text. The upload is rejected with an explanation
  rather than silently producing an empty index; OCR would be needed.
- Single worker process, since the index is held in memory. Scaling horizontally
  would mean moving the index to a shared vector store.
- The similarity threshold was set empirically against a small corpus. The
  nearest out-of-scope question cleared it by 0.01, which is a narrow margin —
  tuning it against a larger set of out-of-scope questions is the next step.
