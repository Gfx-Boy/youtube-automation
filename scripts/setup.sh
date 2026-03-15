#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# setup.sh — One-time setup for the video_ai system on macOS
# ─────────────────────────────────────────────────────────────
set -euo pipefail

echo "══════════════════════════════════════════════"
echo "  Video AI — Environment Setup"
echo "══════════════════════════════════════════════"

cd "$(dirname "$0")"

# ── Check system dependencies ──
echo ""
echo "Checking system dependencies..."

check_cmd() {
    if command -v "$1" &>/dev/null; then
        echo "  ✓ $1 found: $(command -v "$1")"
    else
        echo "  ✗ $1 NOT found — install it first"
        echo "    brew install $1"
        return 1
    fi
}

check_cmd python3
check_cmd ffmpeg
check_cmd ffprobe

# ── Create virtual environment ──
echo ""
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
    echo "  ✓ .venv created"
else
    echo "  ✓ .venv already exists"
fi

# ── Activate and install ──
echo ""
echo "Installing Python dependencies..."
source .venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt -q
pip install yt-dlp -q

echo ""
echo "  ✓ All Python packages installed"

# ── Create .env if missing ──
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "  ✓ Created .env from .env.example (fill in your API keys)"
else
    echo "  ✓ .env already exists"
fi

# ── Ensure directories exist ──
mkdir -p projects weights fonts luts

echo ""
echo "══════════════════════════════════════════════"
echo "  Setup complete!"
echo ""
echo "  Activate:  source .venv/bin/activate"
echo "  CLI:       python -m app.cli --help"
echo "  API:       python -m app.cli serve"
echo "  Generate:  python -m app.cli generate --name 'Test' --audio song.mp3 --urls 'URL'"
echo "══════════════════════════════════════════════"
