# Single-stage build with CPU-only PyTorch (the default torch wheel pulls
# in ~800 MB of CUDA libraries that a local stdio inference server never uses).
FROM python:3.12-slim

LABEL io.modelcontextprotocol.server.name="io.github.vishaltorc/subconscious-mcp"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    SUBCONSCIOUS_STORAGE_DIR=/data

WORKDIR /app

# CPU-only torch in its own layer so source changes don't invalidate this big download.
RUN pip install --index-url https://download.pytorch.org/whl/cpu torch

COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install .

# Pre-cache the embedding model so the first MCP call is sub-second
# instead of waiting on a ~90 MB Hugging Face download.
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

RUN mkdir -p /data

ENTRYPOINT ["subconscious-mcp"]
