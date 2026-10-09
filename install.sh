#!/usr/bin/env bash
# One-step setup for Ligase.
#   ./install.sh              core install (database, literature, pharmacology, biochemistry tools)
#   ./install.sh --genomics   also install the heavy genomics stack (torch, esm, scanpy)
set -euo pipefail

cd "$(dirname "$0")"
BIOMNI_REPO="https://github.com/snap-stanford/biomni.git"
BIOMNI_COMMIT="400c1f3"   # tool library version the benchmarks were run against
EXTRAS="dev"
[[ "${1:-}" == "--genomics" ]] && EXTRAS="dev,genomics"

step() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }

step "1/4  Biomni tool library"
if [[ -d biomni/biomni ]]; then
  echo "found ./biomni"
else
  git clone --quiet "$BIOMNI_REPO" biomni
  git -C biomni checkout --quiet "$BIOMNI_COMMIT"
  echo "cloned $BIOMNI_REPO @ $BIOMNI_COMMIT"
fi

step "2/4  Python environment (.venv)"
if command -v uv >/dev/null 2>&1; then
  [[ -d .venv ]] || uv venv --quiet --python ">=3.10" .venv
  uv pip install --quiet --python .venv/bin/python -e ".[$EXTRAS]"
else
  PY="$(command -v python3.12 || command -v python3.11 || command -v python3.10 || command -v python3)"
  [[ -d .venv ]] || "$PY" -m venv .venv
  .venv/bin/python -m pip install --quiet --upgrade pip
  .venv/bin/python -m pip install --quiet -e ".[$EXTRAS]"
fi
echo "installed: $(.venv/bin/ligase --version)"

step "3/4  Configuration (.env)"
if [[ -f .env ]]; then
  echo "found .env (left unchanged)"
else
  cp .env.example .env
  echo "created .env from .env.example: add GLIMMER_30B_BACKEND or OPENAI_API_KEY"
fi

step "4/4  Health check"
.venv/bin/ligase doctor || true

cat <<'EOF'

Next:
  source .venv/bin/activate
  ligase example apoe4        # a ready-made Alzheimer's genetics study
  ligase                      # ask your own questions
EOF
