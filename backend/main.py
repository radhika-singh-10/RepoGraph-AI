import shutil
import tempfile
import zipfile
from pathlib import Path
from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from models import ExplainRequest, RepoGraph
from analyzer import build_repo_graph, explain_node, generate_pr_markdown, generate_github_action_yaml, audit_solid_principles

app = FastAPI(title="RepoGraph AI")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

LAST_GRAPH = None
LAST_WORKSPACE_DIR = None

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/analyze")
async def analyze_repo(file: UploadFile = File(...)):
    global LAST_GRAPH, LAST_WORKSPACE_DIR

    if not file.filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="Please upload a .zip repository file")

    workdir = tempfile.mkdtemp(prefix="repograph_")
    zip_path = Path(workdir) / file.filename

    try:
        with zip_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        extract_dir = Path(workdir) / "repo"
        extract_dir.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(extract_dir)

        # If ZIP contains a single top-level folder, analyze that folder.
        children = [p for p in extract_dir.iterdir() if p.is_dir()]
        root = children[0] if len(children) == 1 else extract_dir

        # Initialize Git in the local workspace directory
        import subprocess
        try:
            subprocess.run(["git", "init"], cwd=str(root), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(["git", "config", "user.name", "RepoGraph Agent"], cwd=str(root), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(["git", "config", "user.email", "agent@repograph.ai"], cwd=str(root), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(["git", "add", "."], cwd=str(root), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=str(root), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

        graph = build_repo_graph(str(root))
        LAST_GRAPH = graph
        LAST_WORKSPACE_DIR = str(root)
        return graph

    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="Invalid zip file")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/analyze-github")
def analyze_github(url: str):
    global LAST_GRAPH, LAST_WORKSPACE_DIR
    if "github.com" not in url:
        raise HTTPException(status_code=400, detail="Only GitHub URLs are supported.")

    # Sanitize GitHub URLs (auto-extract base repo URL if user pasted a blob/tree link)
    import re
    match = re.match(r'(https?://github\.com/[^/]+/[^/]+)(?:/(?:blob|tree)/.*)?', url)
    if match:
        url = match.group(1).rstrip("/")

    workdir = tempfile.mkdtemp(prefix="repograph_git_")
    try:
        import subprocess
        res = subprocess.run(
            ["git", "clone", "--depth", "1", url, workdir],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=30
        )
        if res.returncode != 0:
            raise HTTPException(status_code=400, detail=f"Failed to clone repository: {res.stderr}")

        # Set Git config inside cloned repository
        subprocess.run(["git", "config", "user.name", "RepoGraph Agent"], cwd=workdir, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["git", "config", "user.email", "agent@repograph.ai"], cwd=workdir, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        graph = build_repo_graph(workdir)
        LAST_GRAPH = graph
        LAST_WORKSPACE_DIR = workdir
        return graph
    except subprocess.TimeoutExpired:
        shutil.rmtree(workdir, ignore_errors=True)
        raise HTTPException(status_code=504, detail="Cloning repository timed out.")
    except Exception as exc:
        shutil.rmtree(workdir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/explain")
def explain(req: ExplainRequest):
    graph = req.graph.model_dump()
    return {"explanation": explain_node(req.node_id, graph)}


@app.post("/pr-report")
def pr_report(req: RepoGraph):
    graph = req.model_dump()
    return {
        "markdown": generate_pr_markdown(graph),
        "github_action": generate_github_action_yaml()
    }


@app.post("/solid-audit")
def solid_audit(req: RepoGraph):
    graph = req.model_dump()
    return audit_solid_principles(graph)


# --- AGENT PULL REQUEST INTERFACE ROUTES ---

class AgentPRRequest(BaseModel):
    instruction: str
    target_file: str = None

@app.post("/agent/create-pr")
def create_pr(req: AgentPRRequest):
    global LAST_WORKSPACE_DIR
    if not LAST_WORKSPACE_DIR:
        from analyzer import init_mock_workspace
        LAST_WORKSPACE_DIR = init_mock_workspace()

    cwd = LAST_WORKSPACE_DIR
    import subprocess
    import random
    import string

    # Ensure repository is on main/master and reset any uncommitted stuff
    base_branch = "main"
    res_branch = subprocess.run(["git", "branch", "--list", "master"], cwd=cwd, capture_output=True, text=True)
    if "master" in res_branch.stdout:
        base_branch = "master"

    try:
        subprocess.run(["git", "checkout", base_branch], cwd=cwd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["git", "reset", "--hard", "HEAD"], cwd=cwd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass

    # Create new agent branch name
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=5))
    branch_name = f"agent/pr-{suffix}"

    try:
        subprocess.run(["git", "checkout", "-b", branch_name], cwd=cwd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to create branch: {str(exc)}")

    # Run multi-agent coding loop
    from analyzer import run_multi_agent_flow
    result = run_multi_agent_flow(cwd, req.instruction, req.target_file)

    # Commit any changes
    try:
        subprocess.run(["git", "add", "."], cwd=cwd, check=True)
        subprocess.run(["git", "commit", "-m", f"agent: {result['pr_title']}"], cwd=cwd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass

    return {
        "branch": branch_name,
        "pr_title": result["pr_title"],
        "pr_body": result["pr_body"],
        "diff": result["diff"],
        "thoughts": result["thoughts"],
        "files_changed": result["files_changed"]
    }


class MergePRRequest(BaseModel):
    branch: str

@app.post("/agent/merge-pr")
def merge_pr(req: MergePRRequest):
    global LAST_WORKSPACE_DIR, LAST_GRAPH
    if not LAST_WORKSPACE_DIR:
        raise HTTPException(status_code=400, detail="No active workspace directory.")

    cwd = LAST_WORKSPACE_DIR
    import subprocess

    base_branch = "main"
    res_branch = subprocess.run(["git", "branch", "--list", "master"], cwd=cwd, capture_output=True, text=True)
    if "master" in res_branch.stdout:
        base_branch = "master"

    try:
        # Checkout base branch
        subprocess.run(["git", "checkout", base_branch], cwd=cwd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        # Merge changes
        subprocess.run(["git", "merge", req.branch], cwd=cwd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to merge branch: {str(exc)}")

    # Re-scan workspace and update graph
    graph = build_repo_graph(cwd)
    LAST_GRAPH = graph
    return graph


# --- TRI-AGENT SUITE API ENDPOINTS ---

@app.post("/agent/validate-spec")
async def validate_spec(spec: str = Form(...), file: UploadFile = File(None)):
    global LAST_WORKSPACE_DIR
    if not LAST_WORKSPACE_DIR:
        from analyzer import init_mock_workspace
        LAST_WORKSPACE_DIR = init_mock_workspace()
        
    image_bytes = None
    if file:
        image_bytes = await file.read()
        
    from analyzer import run_spec_validator_agent
    return run_spec_validator_agent(LAST_WORKSPACE_DIR, spec, image_bytes)


class CIRunRequest(BaseModel):
    branch: str = None

@app.post("/agent/run-ci")
def run_ci(req: CIRunRequest = None):
    global LAST_WORKSPACE_DIR
    if not LAST_WORKSPACE_DIR:
        from analyzer import init_mock_workspace
        LAST_WORKSPACE_DIR = init_mock_workspace()
        
    from analyzer import run_archguard_ci_agent
    branch = req.branch if req and req.branch else "main"
    return run_archguard_ci_agent(LAST_WORKSPACE_DIR, branch)


@app.get("/agent/history")
def git_history():
    global LAST_WORKSPACE_DIR
    if not LAST_WORKSPACE_DIR:
        from analyzer import init_mock_workspace
        LAST_WORKSPACE_DIR = init_mock_workspace()
        
    from analyzer import get_git_history
    return get_git_history(LAST_WORKSPACE_DIR)


class TimeTravelRequest(BaseModel):
    sha: str

@app.post("/agent/time-travel")
def time_travel(req: TimeTravelRequest):
    global LAST_WORKSPACE_DIR
    if not LAST_WORKSPACE_DIR:
        from analyzer import init_mock_workspace
        LAST_WORKSPACE_DIR = init_mock_workspace()
        
    from analyzer import checkout_commit_and_map
    return checkout_commit_and_map(LAST_WORKSPACE_DIR, req.sha)

