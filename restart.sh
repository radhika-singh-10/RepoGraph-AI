#!/bin/bash

# Terminal colors
YELLOW='\033[0;33m'
GREEN='\033[0;32m'
NC='\033[0m' # No Color

echo -e "${YELLOW}Stopping any existing backend (8000) or frontend (5173) processes...${NC}"

# Find and kill process on port 8000
PID_8000=$(lsof -t -i:8000)
if [ -n "$PID_8000" ]; then
    echo "Killing process on port 8000 (PID: $PID_8000)..."
    kill -9 $PID_8000 2>/dev/null || true
fi

# Find and kill process on port 5173
PID_5173=$(lsof -t -i:5173)
if [ -n "$PID_5173" ]; then
    echo "Killing process on port 5173 (PID: $PID_5173)..."
    kill -9 $PID_5173 2>/dev/null || true
fi

echo -e "${GREEN}Starting servers fresh...${NC}"
./run.sh
