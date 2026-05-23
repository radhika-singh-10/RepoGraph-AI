# RepoGraph AI

AI-powered repository architecture visualization MVP.

## Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

## Frontend

```bash
cd frontend
npm install
npm run dev
```

Open the Vite URL, upload a `.zip` repository, paste a public GitHub URL, or click "Load Demo Codebase" to begin.

## Features & Multi-Agent Capabilities

- **Interactive Codebase Maps**: Visualizes code files, HTTP routes, client-side API requests, database models, and utilities in structured column lanes using React Flow.
- **SOLID Design Principles Audit**: Scans code structures to compute architectural health scores and highlights SRP, DIP, or ISP violations with refactoring remedies.
- **Multi-Agent PR Creator (Gemini 3.5 Flash)**:
  - **Architect Agent (Planner)**: Analyzes instructions and codebase files to formulate a change plan.
  - **Coder Agent (Developer)**: Implements the code changes on a new git branch.
  - **Reviewer Agent (QA)**: Evaluates the diff for AST syntax errors, drafts a comprehensive Pull Request description, and verifies design principles compliance.
- **Interactive Agent Console**: Streams real-time thoughts and terminal logs of the collaborating agents.
- **Pull Request & Diff Viewer**: Displays the drafted PR title/description alongside color-coded line-by-line file diffs.
- **Local Merge Integration**: Click "Merge Pull Request" to automatically merge the changes, trigger a codebase re-scan, and refresh the visual architecture graph in real-time.
