FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    LIGASE_CLOUD=1 \
    LIGASE_WEB_MODEL=gpt-6-luna \
    LIGASE_STATE_DIR=/tmp/ligase_state \
    LIGASE_OUTPUT_ROOT=/tmp/ligase_runs \
    CLAW_SANDBOX_PROFILE=workspace \
    PORT=8080

WORKDIR /app

# Copy package metadata first so third-party dependency wheels stay cached across code updates
COPY pyproject.toml README.md LICENSE ./
RUN mkdir -p ligase && printf '__version__ = "0.0.0"\n' > ligase/__init__.py \
    && pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir ".[providers,web]"

# Copy application & Biomni sources and pre-compile all .pyc bytecode for fast cold-boot
COPY ligase ./ligase
COPY biomni/biomni ./biomni/biomni

RUN pip install --no-cache-dir --no-deps . \
    && python -m compileall -q /usr/local/lib/python3.12 /app/ligase /app/biomni \
    && python -c "import ligase, ligase.webapp.server; print('Ligase WebApp verified:', ligase.__version__)"

RUN useradd --create-home --uid 10001 ligase \
    && mkdir -p /tmp/ligase_state /tmp/ligase_runs \
    && chown -R 10001:10001 /app /tmp/ligase_state /tmp/ligase_runs

USER ligase
EXPOSE 8080

CMD ["sh", "-c", "exec python -m uvicorn ligase.webapp.server:app --host 0.0.0.0 --port ${PORT:-8080} --workers 1"]
