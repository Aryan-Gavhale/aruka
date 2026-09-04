#!/bin/bash
# Run once on PythonAnywhere, in a Bash console, from your home directory.
#   bash aruka/deploy/setup_pythonanywhere.sh
#
# Prerequisite: git clone https://github.com/Aryan-Gavhale/aruka.git

set -euo pipefail

cd "$(dirname "$0")/.."
ROOT="$(pwd)"

echo "==> Aruka setup in $ROOT"

if [[ ! -f requirements.txt ]]; then
  echo "requirements.txt not found. Run this from inside the cloned aruka folder."
  exit 1
fi

PYTHON="${PYTHON:-python3.12}"
if ! command -v "$PYTHON" &>/dev/null; then
  PYTHON=python3.11
fi
if ! command -v "$PYTHON" &>/dev/null; then
  PYTHON=python3.10
fi

echo "==> Using $PYTHON"
$PYTHON -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

mkdir -p db static/uploads backups

if [[ ! -f config.json ]]; then
  cp deploy/config.pythonanywhere.example.json config.json
  echo ""
  echo "Created config.json — edit it before seeding:"
  echo "  - owner_email"
  echo "  - owner_password"
  echo "  - public_base_url  (https://YOURUSERNAME.pythonanywhere.com)"
  echo "  - secret_key       (long random string)"
  echo ""
  echo "Then run:  source .venv/bin/activate && python app.py seed"
  exit 0
fi

echo "==> Seeding database"
python app.py seed

echo ""
echo "Done. Next:"
echo "  1. Web tab → Manual configuration → Python 3.12 (or 3.11)"
echo "  2. Source code: $ROOT"
echo "  3. Virtualenv:   $ROOT/.venv"
echo "  4. WSGI file:    copy deploy/pythonanywhere_wsgi.py (edit YOURUSERNAME)"
echo "  5. Static files: /static/ → $ROOT/static/"
echo "  6. Reload the web app"
echo "  7. Open https://YOURUSERNAME.pythonanywhere.com/admin"
