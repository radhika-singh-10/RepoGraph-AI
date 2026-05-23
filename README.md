# RepoGraph AI

AI-powered repository architecture visualization MVP.

## Quick Start

You can run both the frontend and backend servers concurrently using the provided startup scripts:

### Start both servers
To install dependencies (if not already installed) and launch the application:
```bash
./run.sh
```

### Restart/Reset servers
If you need to force-restart the servers or free up ports 8000 and 5173:
```bash
./restart.sh
```

> [!NOTE]
> **Live Reloading**:
> - The **Backend** runs with hot reloading (`uvicorn --reload`), so any changes to Python files will automatically reload the server.
> - The **Frontend** uses Vite's Instant Hot Module Replacement (HMR), so frontend code changes are instantly reflected in the browser upon saving.


Open the Vite URL, upload a `.zip` repository, paste a public GitHub URL, or click "Load Demo Codebase" to begin.

## Features & Multi-Agent Capabilities

- **Agentic Graph Builder (Orchestrator + Parallel Workers)**:
  - **Parallel File Analyzers**: Spawns concurrent Gemini 3.5 Flash requests (utilizing a `ThreadPoolExecutor`) to scan files and extract semantic declarations, technologies, and roles using structured Pydantic schemas.
  - **Graph Orchestrator Agent**: Aggregates worker scans to dynamically resolve imports, route handlers (`defines` relation), and client requests (`calls` relation), compiling a complete visual graph schema.
  - **Local Fallback**: Automatically reverts to quick AST/regex scanning when the API key is not present.
- **SOLID Design Principles Audit**: Analyzes modular cohesion to compute architectural scores and highlights design violations with remedy proposals.
- **Multi-Agent PR Creator with Gemini Tool Calling**:
  - **Architect Agent (Planner)**: Uses search and read tools (`list_directory`, `read_file_content`, `search_codebase`) to inspect files and create a change plan.
  - **Coder Agent (Developer)**: Employs writing and sandbox terminal checks (`write_file_content`, `run_command`) to edit code files and compile changes in a secure branch environment.
  - **Reviewer Agent (QA)**: Analyzes diffs, checks AST parsing, and drafts GitHub Pull Request description logs.
- **Interactive Agent Console**: Streams monospaced agent conversation logs and tool invocation traces in real-time.
- **PR Diff Viewer & Merge Loop**: Displays color-coded diff highlights and supports local git merges to re-scan and refresh codebase graphs in a single click.
