#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
#  MiroFish Lite — One-command startup
#  Usage: ./start.sh [--no-browser]
#
#  Starts the Flask backend (port 5001) and the Vite frontend
#  (port 5173 by default) and streams live logs from both.
# ═══════════════════════════════════════════════════════════════

set -euo pipefail

# ── Colours ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
RESET='\033[0m'

ok()   { echo -e "  ${GREEN}✔${RESET}  $*"; }
info() { echo -e "  ${CYAN}→${RESET}  $*"; }
warn() { echo -e "  ${YELLOW}⚠${RESET}  $*"; }
fail() { echo -e "\n  ${RED}✖  ERROR:${RESET} $*\n"; exit 1; }

# ── Resolve root directory (works from any CWD) ───────────────────────────────
ROOT="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$ROOT/backend"
FRONTEND_DIR="$ROOT/frontend"
LOG_DIR="$ROOT/.logs"
mkdir -p "$LOG_DIR"

BACKEND_LOG="$LOG_DIR/backend.log"
FRONTEND_LOG="$LOG_DIR/frontend.log"

BACKEND_PORT="${FLASK_PORT:-5001}"
BACKEND_HOST="${FLASK_HOST:-0.0.0.0}"

# ── Parse flags ───────────────────────────────────────────────────────────────
OPEN_BROWSER=true
for arg in "$@"; do
  [[ "$arg" == "--no-browser" ]] && OPEN_BROWSER=false
done

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo ""
echo -e "  ${BOLD}${CYAN}🐟  MiroFish Lite${RESET}"
echo    "  ─────────────────────────────────────────────"
echo ""

# ── 1. Prerequisite checks ────────────────────────────────────────────────────
info "Checking prerequisites…"

command -v uv  >/dev/null 2>&1 || fail "'uv' not found. Install it: https://docs.astral.sh/uv/getting-started/installation/"
command -v node >/dev/null 2>&1 || fail "'node' not found. Install Node.js: https://nodejs.org"
command -v npm  >/dev/null 2>&1 || fail "'npm' not found. Install Node.js: https://nodejs.org"

ok "uv  $(uv --version 2>&1 | head -1)"
ok "node $(node --version)"
ok "npm  $(npm --version)"
echo ""

# ── 2. .env existence check ───────────────────────────────────────────────────
if [[ ! -f "$ROOT/.env" ]]; then
  warn "No .env file found at project root."
  if [[ -f "$ROOT/.env.example" ]]; then
    info "Copying .env.example → .env  (please fill in your keys)"
    cp "$ROOT/.env.example" "$ROOT/.env"
    warn "Edit $ROOT/.env with your GEMINI_API_KEY, SUPABASE_URL and SUPABASE_KEY, then re-run ./start.sh"
    exit 1
  else
    fail ".env file is missing and no .env.example was found. Please create $ROOT/.env"
  fi
fi

# Quick sanity-check: make sure the three required keys are present & non-empty
check_env_key() {
  local key="$1"
  local val
  val=$(grep -E "^${key}=" "$ROOT/.env" | cut -d= -f2- | tr -d '[:space:]')
  if [[ -z "$val" || "$val" == *"your_"* || "$val" == *"change-me"* ]]; then
    fail "Missing or placeholder value for '${key}' in .env. Please set it before starting."
  fi
}
check_env_key "GEMINI_API_KEY"
check_env_key "SUPABASE_URL"
check_env_key "SUPABASE_KEY"
ok ".env looks good"
echo ""

# ── 3. Install frontend dependencies if needed ────────────────────────────────
if [[ ! -d "$FRONTEND_DIR/node_modules" ]]; then
  info "node_modules not found — running npm install in frontend/…"
  (cd "$FRONTEND_DIR" && npm install --silent) || fail "npm install failed"
  ok "Frontend dependencies installed"
  echo ""
fi

# ── 4. Start backend ──────────────────────────────────────────────────────────
info "[1/2] Starting backend  (Flask + Gemini + Supabase)…"
(cd "$BACKEND_DIR" && uv run python run.py) > "$BACKEND_LOG" 2>&1 &
BACKEND_PID=$!

# Health-check loop: wait up to 20 s for the backend to respond
BACKEND_READY=false
for i in $(seq 1 20); do
  if kill -0 "$BACKEND_PID" 2>/dev/null && \
     curl -sf "http://localhost:${BACKEND_PORT}/api/health" >/dev/null 2>&1; then
    BACKEND_READY=true
    break
  fi
  # If the process died, abort early
  if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
    echo ""
    warn "Backend process exited unexpectedly. Last log lines:"
    tail -20 "$BACKEND_LOG" | sed 's/^/    /'
    fail "Backend failed to start. Check $BACKEND_LOG for details."
  fi
  sleep 1
done

if [[ "$BACKEND_READY" == false ]]; then
  warn "Backend didn't respond on port ${BACKEND_PORT} within 20 s."
  warn "Continuing anyway — it may still be warming up."
  warn "Check logs: $BACKEND_LOG"
else
  ok "Backend is ready on http://localhost:${BACKEND_PORT}"
fi
echo ""

# ── 5. Start frontend ─────────────────────────────────────────────────────────
info "[2/2] Starting frontend (Vue 3 + Vite)…"
(cd "$FRONTEND_DIR" && npm run dev) > "$FRONTEND_LOG" 2>&1 &
FRONTEND_PID=$!

# Give Vite a moment to print its bound URL, then extract the port it chose
sleep 3

# Vite prints something like:  ➜  Local:   http://localhost:5173/
FRONTEND_URL=$(grep -oE 'http://localhost:[0-9]+' "$FRONTEND_LOG" | head -1 || true)
FRONTEND_URL="${FRONTEND_URL:-http://localhost:5173}"

if ! kill -0 "$FRONTEND_PID" 2>/dev/null; then
  echo ""
  warn "Frontend process exited unexpectedly. Last log lines:"
  tail -20 "$FRONTEND_LOG" | sed 's/^/    /'
  fail "Frontend failed to start. Check $FRONTEND_LOG for details."
fi
ok "Frontend is ready on $FRONTEND_URL"
echo ""

# ── 6. Summary ────────────────────────────────────────────────────────────────
echo    "  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "  ${GREEN}${BOLD}✅  MiroFish Lite is running!${RESET}"
echo    "  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo    ""
echo -e "  🌐  ${BOLD}Frontend${RESET}  →  ${CYAN}${FRONTEND_URL}${RESET}"
echo -e "  ⚙️   ${BOLD}Backend${RESET}   →  ${CYAN}http://localhost:${BACKEND_PORT}${RESET}"
echo    ""
echo -e "  📋  Backend log   →  ${LOG_DIR}/backend.log"
echo -e "  📋  Frontend log  →  ${LOG_DIR}/frontend.log"
echo    ""
echo    "  Press Ctrl+C to stop everything."
echo    ""

# ── Open browser (macOS) ──────────────────────────────────────────────────────
if [[ "$OPEN_BROWSER" == true ]] && command -v open >/dev/null 2>&1; then
  open "$FRONTEND_URL" 2>/dev/null || true
fi

# ── 7. Graceful shutdown on Ctrl+C ────────────────────────────────────────────
cleanup() {
  echo ""
  echo -e "  ${YELLOW}⏹  Shutting down MiroFish Lite…${RESET}"

  # Kill the process groups so child threads also die
  kill -- -"$BACKEND_PID"  2>/dev/null || kill "$BACKEND_PID"  2>/dev/null || true
  kill -- -"$FRONTEND_PID" 2>/dev/null || kill "$FRONTEND_PID" 2>/dev/null || true

  wait "$BACKEND_PID"  2>/dev/null || true
  wait "$FRONTEND_PID" 2>/dev/null || true

  echo -e "  ${GREEN}✔  All processes stopped. Goodbye!${RESET}"
  echo ""
  exit 0
}

trap cleanup INT TERM

# Keep the shell alive, streaming both logs to the terminal
tail -f "$BACKEND_LOG" "$FRONTEND_LOG" &
TAIL_PID=$!

wait "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null || true
kill "$TAIL_PID" 2>/dev/null || true
