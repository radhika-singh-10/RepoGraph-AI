#!/bin/bash

# Exit on error
set -e

# Terminal colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Project root directory
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Cleanup function – kills both servers
cleanup() {
    echo -e "\n${BLUE}Stopping servers...${NC}"
    if [ -n "$BACKEND_PID" ]; then
        kill "$BACKEND_PID" 2>/dev/null || true
    fi
    if [ -n "$FRONTEND_PID" ]; then
        kill "$FRONTEND_PID" 2>/dev/null || true
    fi
    exit 0
}

# Trap signals for graceful shutdown
trap cleanup INT TERM EXIT

echo -e "${GREEN}Starting RepoGraph AI...${NC}"

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

# Start FastAPI server using module path
echo -e "${GREEN}Starting Backend Server on port 8000...${NC}"
uvicorn backend.main:app --reload --port 8000 > "$PROJECT_DIR/backend/backend.log" 2>&1 &
BACKEND_PID=$!

# ---------- Frontend ----------
echo -e "${BLUE}Setting up Frontend...${NC}"
if [ ! -d "$PROJECT_DIR/frontend/node_modules" ]; then
    echo "Installing frontend dependencies..."
    cd "$PROJECT_DIR/frontend" && npm install
fi
cd "$PROJECT_DIR/frontend"

echo -e "${GREEN}Starting Frontend Dev Server...${NC}"
npm run dev > "$PROJECT_DIR/frontend/frontend.log" 2>&1 &
FRONTEND_PID=$!

# Wait for both processes (or until killed)
wait $BACKEND_PID $FRONTEND_PID
cleanup
