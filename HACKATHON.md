# Hackathon Submission Details: RepoGraph AI

This document clearly distinguishes between the pre-existing MVP base and the **new work built during this Google I/O Hackathon**.

---

## 📅 Chronology of Contributions

### 1. Pre-Existing Base (Before the Hackathon)
- Simple local `.zip` file upload.
- Basic, static parser mapping local files using standard Python AST and Javascript regex.
- Simple, un-interactive React Flow canvas displaying columns.
- Static, pre-compiled markdown Pull Request template placeholder.

### 2. Hackathon Additions (Created During the Event) 🚀
During the hackathon, we migrated the static scanner and template compiler into a fully agentic, multi-agent development and codebase mapping platform powered by **Gemini 3.5 Flash**:

#### A. Agentic Graph Mapping Engine
- **Concurrent File Analyzer Agents**: Refactored file scanning. The system now spawns concurrent `gemini-3.5-flash` requests (using a `ThreadPoolExecutor`) to evaluate code files semantically, extracting exports, imports, and technologies using structured Pydantic response schemas.
- **Graph Orchestrator Agent**: Aggregates analyzer outputs to resolve import paths, match client API requests to HTTP routes, and output the complete codebase graph node/edge configuration alongside a detailed summary.

#### B. Multi-Agent PR Creator with Gemini Tool Calling
- Implemented a collaborative developer team consisting of three specialized agents:
  - **Architect Agent (Planner)**: Explores target codebase sections and compiles logical refactoring plans.
  - **Coder Agent (Developer)**: Edits files and runs terminal tests in the sandbox.
  - **Reviewer Agent (QA)**: Validates code syntax (AST compile check) and drafts comprehensive GitHub Pull Request reports.
- **Function Calling (Tools)**: Integrated sandbox tools directly into the agents' execution loops, allowing them to autonomously use:
  - `list_directory`: Explore the filesystem.
  - `read_file_content`: Read code contents.
  - `write_file_content`: Overwrite/create files.
  - `search_codebase`: Query variables/functions.
  - `run_command`: Execute terminal commands (e.g. `py_compile` checks) within the workspace sandbox.

#### C. Interactive Agent Console & Git Diff Dashboard
- **CLI Terminal Emulator**: Added a monospaced terminal panel to the UI that streams real-time agent thought logs and tool call updates.
- **Color-Coded Git Diff Viewer**: Parses git diff payloads to display line-by-line file modifications (green for additions, red for deletions).
- **Local Git Merge Loop**: Integrated a direct "Merge Pull Request" action that checks out the main branch, merges the agent's branch locally, re-scans the folder, and re-renders the React Flow graph in real-time.

#### D. Interactive SOLID Design Audit
- Scans modular health, calculates design scores, and renders interactive violation cards with direct "⚡ Auto-Fix" triggers that feed instructions directly into the AI Code Agent tab.
