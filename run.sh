#!/bin/bash

# Exit on error
set -e

# Terminal colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Project root directory
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"

kill_process_tree() {
    local pid=$1
    [ -z "$pid" ] && return
    local children
    children=$(pgrep -P "$pid" 2>/dev/null || true)
    for child in $children; do
        kill_process_tree "$child"
    done
    kill "$pid" 2>/dev/null || true
}

free_port() {
    local port=$1
    local pids
    pids=$(lsof -ti tcp:"$port" 2>/dev/null || true)
    if [ -n "$pids" ]; then
        if [ "${2:-}" != "quiet" ]; then
            echo -e "${BLUE}Port ${port} in use; stopping existing process(es)...${NC}"
        fi
        kill $pids 2>/dev/null || true
        sleep 0.5
        pids=$(lsof -ti tcp:"$port" 2>/dev/null || true)
        if [ -n "$pids" ]; then
            kill -9 $pids 2>/dev/null || true
        fi
    fi
}

# Cleanup function – kills both servers and frees their ports
cleanup() {
    echo -e "\n${BLUE}Stopping servers...${NC}"
    kill_process_tree "$BACKEND_PID"
    kill_process_tree "$FRONTEND_PID"
    sleep 0.5
    free_port "$BACKEND_PORT" quiet
    free_port "$FRONTEND_PORT" quiet
    exit 0
}

# Trap signals for graceful shutdown
trap cleanup INT TERM EXIT

echo -e "${GREEN}Starting RepoGraph AI...${NC}"

# Load local secrets (GEMINI_API_KEY, etc.)
if [ -f "$PROJECT_DIR/.env" ]; then
    set -a
    # shellcheck disable=SC1091
    source "$PROJECT_DIR/.env"
    set +a
fi

# ---------- Backend ----------
echo -e "${BLUE}Setting up Backend...${NC}"
# Ensure virtual environment exists
if [ ! -d "$PROJECT_DIR/backend/.venv" ]; then
    echo "Creating Python virtual environment (.venv)..."
    python3 -m venv "$PROJECT_DIR/backend/.venv"
fi
source "$PROJECT_DIR/backend/.venv/bin/activate"
pip install --upgrade pip
pip install -r "$PROJECT_DIR/backend/requirements.txt"

free_port "$BACKEND_PORT"

# Start FastAPI server using module path
echo -e "${GREEN}Starting Backend Server on port ${BACKEND_PORT}...${NC}"
uvicorn backend.main:app --reload --port "$BACKEND_PORT" > "$PROJECT_DIR/backend/backend.log" 2>&1 &
BACKEND_PID=$!

# Confirm backend actually bound to the port
BACKEND_READY=false
for _ in $(seq 1 20); do
    if curl -sf "http://localhost:${BACKEND_PORT}/health" >/dev/null 2>&1; then
        BACKEND_READY=true
        break
    fi
    if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
        echo -e "${BLUE}Backend failed to start. See backend/backend.log:${NC}"
        tail -5 "$PROJECT_DIR/backend/backend.log" 2>/dev/null || true
        exit 1
    fi
    sleep 0.25
done

if [ "$BACKEND_READY" = false ]; then
    echo -e "${BLUE}Backend did not become ready on port ${BACKEND_PORT}. See backend/backend.log:${NC}"
    tail -5 "$PROJECT_DIR/backend/backend.log" 2>/dev/null || true
    exit 1
fi

# ---------- Frontend ----------
echo -e "${BLUE}Setting up Frontend...${NC}"
if [ ! -d "$PROJECT_DIR/frontend/node_modules" ]; then
    echo "Installing frontend dependencies..."
    cd "$PROJECT_DIR/frontend" && npm install
fi
cd "$PROJECT_DIR/frontend"

free_port "$FRONTEND_PORT"

echo -e "${GREEN}Starting Frontend Dev Server on port ${FRONTEND_PORT}...${NC}"
npm run dev -- --port "$FRONTEND_PORT" > "$PROJECT_DIR/frontend/frontend.log" 2>&1 &
FRONTEND_PID=$!

# Wait for Vite to print its URL, then show where to open the app
for _ in $(seq 1 20); do
    FRONTEND_URL=$(grep -oE 'http://localhost:[0-9]+/' "$PROJECT_DIR/frontend/frontend.log" 2>/dev/null | head -1)
    if [ -n "$FRONTEND_URL" ]; then
        break
    fi
    sleep 0.25
done

echo ""
echo -e "${GREEN}Servers running:${NC}"
echo -e "  Backend:  http://localhost:${BACKEND_PORT}"
if [ -n "$FRONTEND_URL" ]; then
    echo -e "  Frontend: ${FRONTEND_URL}"
else
    echo -e "  Frontend: http://localhost:${FRONTEND_PORT} (see frontend/frontend.log if unavailable)"
fi
echo ""

# Wait for both processes (or until killed)
wait $BACKEND_PID $FRONTEND_PID
cleanup
