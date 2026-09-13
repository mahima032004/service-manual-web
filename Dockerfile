FROM python:3.11-slim

RUN useradd -m -u 1000 user
USER user
ENV PATH="/home/user/.local/bin:$PATH" \
    HF_HOME=/home/user/.cache/huggingface \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

COPY --chown=user . .

# Bake the embedding model into the image so the first request isn't slow
RUN python -c "from fastembed import TextEmbedding; \
TextEmbedding('sentence-transformers/all-MiniLM-L6-v2')"

EXPOSE 7860

# One worker: the index and uploaded documents live in process memory
CMD gunicorn --bind 0.0.0.0:${PORT:-7860} --workers 1 --threads 4 --timeout 180 app:app
