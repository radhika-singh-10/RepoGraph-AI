#!/bin/bash

# Exit on error
set -e

# Terminal colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Project directory
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Function to clean up background processes on exit
cleanup() {
    echo -e "\n${BLUE}Stopping backend server...${NC}"
    if [ -n "$BACKEND_PID" ]; then
        kill "$BACKEND_PID" 2>/dev/null || true
    fi
    exit 0
}

# Trap Ctrl+C and exit signals
trap cleanup INT TERM EXIT

echo -e "${GREEN}Starting RepoGraph AI...${NC}"

# 1. Setup and Start Backend
echo -e "${BLUE}Setting up Backend...${NC}"
cd "$PROJECT_DIR/backend"

if [ ! -d ".venv" ]; then
    echo "Creating Python virtual environment (.venv)..."
    python3 -m venv .venv
fi

echo "Activating virtual environment and installing dependencies..."
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo -e "${GREEN}Starting Backend Server on port 8000...${NC}"
uvicorn main:app --reload --port 8000 &
BACKEND_PID=$!

# 2. Setup and Start Frontend
echo -e "${BLUE}Setting up Frontend...${NC}"
cd "$PROJECT_DIR/frontend"

if [ ! -d "node_modules" ]; then
    echo "node_modules not found. Installing frontend dependencies..."
    npm install
fi

echo -e "${GREEN}Starting Frontend Dev Server...${NC}"
npm run dev
