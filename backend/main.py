import shutil
import tempfile
import zipfile
import os
import subprocess
import random
import string
import re
import requests
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from .models import ExplainRequest, RepoGraph
from .analyzer import (
    audit_solid_principles,
    build_repo_graph,
    checkout_commit_and_map,
    explain_node,
    generate_github_action_yaml,
    generate_readme_markdown,
    generate_pr_markdown,
    get_git_history,
    init_mock_workspace,
    run_archguard_ci_agent,
    run_multi_agent_flow,
    run_spec_validator_agent,
)


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
LAST_AGENT_PR = None

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

    # Check if the scanned URL corresponds to the active local RepoGraph AI workspace
    local_repo_path = Path(__file__).resolve().parent.parent
    if "repograph-ai" in url.lower():
        LAST_WORKSPACE_DIR = str(local_repo_path)
        graph = build_repo_graph(str(local_repo_path))
        LAST_GRAPH = graph
        return graph

    workdir = tempfile.mkdtemp(prefix="repograph_git_")
    try:
        import subprocess
        # Clone without "--depth 1" to retain the full git commit history for time-travel scrubbing
        res = subprocess.run(
            ["git", "clone", url, workdir],
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


@app.post("/readme-report")
def readme_report(req: RepoGraph):
    graph = req.model_dump()
    return {
        "markdown": generate_readme_markdown(graph),
        "github_action": generate_github_action_yaml()
    }


@app.post("/pr-report")
def pr_report(req: RepoGraph):
    """Deprecated alias — use /readme-report."""
    return readme_report(req)


@app.post("/solid-audit")
def solid_audit(req: RepoGraph):
    graph = req.model_dump()
    return audit_solid_principles(graph)
@app.post("/analyze-demo")
def analyze_demo():
    """Build and return a demo codebase graph for first-time / offline use."""
    global LAST_GRAPH, LAST_WORKSPACE_DIR
    LAST_WORKSPACE_DIR = init_mock_workspace()
    graph = build_repo_graph(LAST_WORKSPACE_DIR)
    LAST_GRAPH = graph
    return graph


@app.get("/graph")
def get_graph():
    """Return the latest generated repository graph for the frontend.
    Bootstraps the demo codebase graph on first request if none exists yet.
    """
    global LAST_GRAPH, LAST_WORKSPACE_DIR
    if LAST_GRAPH is None:
        LAST_WORKSPACE_DIR = init_mock_workspace()
        graph = build_repo_graph(LAST_WORKSPACE_DIR)
        LAST_GRAPH = graph
    return LAST_GRAPH



# --- AGENT PULL REQUEST INTERFACE ROUTES ---

class AgentPRRequest(BaseModel):
    instruction: str
    target_file: Optional[str] = None

@app.post("/agent/create-pr")
def create_pr(req: AgentPRRequest):
    global LAST_WORKSPACE_DIR, LAST_AGENT_PR
    if not LAST_WORKSPACE_DIR:
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
    result = run_multi_agent_flow(cwd, req.instruction, req.target_file)

    # Commit any changes
    try:
        subprocess.run(["git", "add", "."], cwd=cwd, check=True)
        subprocess.run(["git", "commit", "-m", f"agent: {result['pr_title']}"], cwd=cwd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass

    LAST_AGENT_PR = {"branch": branch_name, "url": None}

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
        LAST_WORKSPACE_DIR = init_mock_workspace()
        
    image_bytes = None
    if file:
        image_bytes = await file.read()
        
    return run_spec_validator_agent(LAST_WORKSPACE_DIR, spec, image_bytes)


class CIRunRequest(BaseModel):
    branch: str = None

@app.post("/agent/run-ci")
def run_ci(req: CIRunRequest = None):
    global LAST_WORKSPACE_DIR
    if not LAST_WORKSPACE_DIR:
        LAST_WORKSPACE_DIR = init_mock_workspace()
        
    branch = req.branch if req and req.branch else "main"
    return run_archguard_ci_agent(LAST_WORKSPACE_DIR, branch)


@app.get("/agent/history")
def git_history():
    global LAST_WORKSPACE_DIR
    if not LAST_WORKSPACE_DIR:
        LAST_WORKSPACE_DIR = init_mock_workspace()
        
    return get_git_history(LAST_WORKSPACE_DIR)


class TimeTravelRequest(BaseModel):
    sha: str

@app.post("/agent/time-travel")
def time_travel(req: TimeTravelRequest):
    global LAST_WORKSPACE_DIR
    if not LAST_WORKSPACE_DIR:
        LAST_WORKSPACE_DIR = init_mock_workspace()
        
    return checkout_commit_and_map(LAST_WORKSPACE_DIR, req.sha)


class PushPRRequest(BaseModel):
    branch: Optional[str] = None
    title: Optional[str] = "AI generated PR"
    body: Optional[str] = "Generated by RepoGraph AI agents."
    token: Optional[str] = None

@app.post("/agent/push-and-create-pr")
def push_and_create_pr(req: Optional[PushPRRequest] = None):
    global LAST_WORKSPACE_DIR, LAST_AGENT_PR
    if not LAST_WORKSPACE_DIR:
        LAST_WORKSPACE_DIR = init_mock_workspace()
        
    cwd = LAST_WORKSPACE_DIR
    
    # 1. Determine branch name – reuse previous if still open
    branch_name = None
    if req and req.branch:
        branch_name = req.branch
    elif LAST_AGENT_PR and LAST_AGENT_PR.get("branch"):
        # Verify that the PR is still open on GitHub
        token = req.token if req and req.token else os.getenv("GITHUB_PAT")
        if token:
            owner_repo = "radhika-singh-10/RepoGraph-AI"
            api_url = f"https://api.github.com/repos/{owner_repo}/pulls?head={owner_repo.split('/')[0]}:{LAST_AGENT_PR['branch']}"
            headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
            resp = requests.get(api_url, headers=headers)
            if resp.status_code == 200 and resp.json():
                # PR exists and is open – reuse it
                branch_name = LAST_AGENT_PR["branch"]
        # fallback if verification fails
        if not branch_name:
            branch_name = None

    if not branch_name:
        # Generate a fresh branch name
        import random
        import string
        suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=5))
        branch_name = f"agent/pr-{suffix}"

    # Ensure we are on the correct branch locally
    try:
        subprocess.run(["git", "checkout", branch_name], cwd=cwd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    except Exception:
        # Branch may not exist locally – create it from base
        base_branch = "main"
        subprocess.run(["git", "checkout", "-b", branch_name, base_branch], cwd=cwd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    # Push branch to origin
    push_res = subprocess.run(["git", "push", "origin", branch_name], cwd=cwd, capture_output=True, text=True)

    # 2. Parse owner/repo from remote URL
    res_remote = subprocess.run(["git", "remote", "get-url", "origin"], cwd=cwd, capture_output=True, text=True)
    remote_url = res_remote.stdout.strip()
    owner_repo = "radhika-singh-10/RepoGraph-AI"  # default fallback
    match = re.search(r'github\.com[:/]([^/]+/[^/.]+)', remote_url)
    if match:
        owner_repo = match.group(1).replace(".git", "")

    # 3. Create PR via GitHub API if token provided
    token = os.getenv("GITHUB_PAT")
    if req and req.token:
        token = req.token
    pr_url = None
    if token:
        api_url = f"https://api.github.com/repos/{owner_repo}/pulls"
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
        payload = {
            "title": req.title if req and req.title else "AI generated PR",
            "head": branch_name,
            "base": "main",
            "body": req.body if req and req.body else "Generated by RepoGraph AI agents."
        }
        resp = requests.post(api_url, json=payload, headers=headers)
        if resp.status_code == 201:
            pr_url = resp.json().get("html_url")
            # Remember this PR for future updates
            LAST_AGENT_PR = {"branch": branch_name, "url": pr_url}
        else:
            pr_url = f"Error creating PR: {resp.status_code} {resp.text}"
    else:
        # fallback to GitHub compare URL
        pr_url = f"https://github.com/{owner_repo}/compare/main...{branch_name}?expand=1"
        # Store for future reuse (even without token we can still push to same branch)
        LAST_AGENT_PR = {"branch": branch_name, "url": pr_url}

    return {
        "success": True,
        "branch": branch_name,
        "github_url": pr_url,
        "output": push_res.stdout or push_res.stderr
    }

@app.post("/agent/complete-pr")
async def complete_pr(req: AgentPRRequest):
    """Run SOLID audit, ArchGuard CI, Spec validator, then create PR via agent flow and push it.
    Returns combined results and a PR URL.
    """
    global LAST_WORKSPACE_DIR, LAST_GRAPH
    if not LAST_WORKSPACE_DIR:
        LAST_WORKSPACE_DIR = init_mock_workspace()
        LAST_GRAPH = build_repo_graph(LAST_WORKSPACE_DIR)

    # 1. SOLID audit
    solid_res = audit_solid_principles(LAST_GRAPH)

    # 2. ArchGuard CI (default branch "main")
    archguard_res = run_archguard_ci_agent(LAST_WORKSPACE_DIR, "main")

    # 3. Spec validator – placeholder spec
    spec_res = run_spec_validator_agent(LAST_WORKSPACE_DIR, "spec placeholder", None)

    # 4. AI Agent – reuse existing create_pr logic to generate a branch and commit changes
    agent_result = create_pr(req)  # returns dict with 'branch' and other info
    branch_name = agent_result.get("branch")

    # 5. Push the newly created branch and obtain PR URL
    push_result = push_and_create_pr(PushPRRequest(branch=branch_name))

    return {
        "solid_audit": solid_res,
        "archguard_ci": archguard_res,
        "spec_validator": spec_res,
        "agent": agent_result,
        "pr": push_result,
    }



# --- FASTAPI MCP HTTP-SSE HANDLER ENDPOINTS ---

@app.post("/mcp")
async def mcp_post_endpoint(req: dict):
    """Exposes JSON-RPC MCP tools directly over HTTP to resolve IDE client discovery 404s."""
    global LAST_WORKSPACE_DIR
    if not LAST_WORKSPACE_DIR:
        LAST_WORKSPACE_DIR = init_mock_workspace()
        
    method = req.get("method")
    req_id = req.get("id")
    
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "serverInfo": {
                    "name": "repograph-ai-mcp",
                    "version": "1.0.0"
                }
            }
        }
        
    elif method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "tools": [
                    {
                        "name": "run_archguard_ci",
                        "description": "Compares base branch vs current branch to check architectural regressions & SOLID compliance.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "branch": {"type": "string"}
                            }
                        }
                    },
                    {
                        "name": "validate_spec",
                        "description": "Compares design specifications against codebase graph.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "spec_text": {"type": "string"}
                            },
                            "required": ["spec_text"]
                        }
                    }
                ]
            }
        }
        
    elif method == "tools/call":
        params = req.get("params", {})
        tool_name = params.get("name")
        args = params.get("arguments", {})
        
        try:
            if tool_name == "run_archguard_ci":
                branch = args.get("branch", "main")
                res = run_archguard_ci_agent(LAST_WORKSPACE_DIR, branch)
                text = f"Regression Score: {res.get('regression_score')}% - Passed: {res.get('passed')}"
            elif tool_name == "validate_spec":
                spec_text = args.get("spec_text")
                res = run_spec_validator_agent(LAST_WORKSPACE_DIR, spec_text)
                text = f"Alignment Score: {res.get('score')}%"
            else:
                text = f"Unknown tool {tool_name}"
                
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": text}]
                }
            }
        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32603, "message": str(e)}
            }
            
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": "Method not found"}}


@app.get("/mcp")
def mcp_get_endpoint():
    return {"status": "ok", "message": "RepoGraph AI MCP Server HTTP endpoint is active."}

@app.get("/.well-known/oauth-protected-resource/mcp")
def oauth_mcp_discovery():
    return {"status": "ok"}

@app.get("/.well-known/oauth-protected-resource")
def oauth_discovery():
    return {"status": "ok"}

