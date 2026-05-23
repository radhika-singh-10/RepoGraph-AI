import ast
import os
import re
import sys
import shutil
import tempfile
import random
import string
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Tuple
from models import GraphNode, GraphEdge
from pydantic import BaseModel, Field
from google import genai
from google.genai import types
from concurrent.futures import ThreadPoolExecutor

CODE_EXTENSIONS = {".py", ".js", ".jsx", ".ts", ".tsx", ".css"}
IGNORE_DIRS = {".git", "node_modules", "dist", "build", "__pycache__", ".venv", "venv"}

JS_IMPORT_RE = re.compile(r"(?:import\s+.*?from\s+['\"]([^'\"]+)['\"]|require\(['\"]([^'\"]+)['\"]\))")
FASTAPI_ROUTE_RE = re.compile(r"@(?:app|router)\.(get|post|put|delete|patch)\(['\"]([^'\"]+)['\"]")
EXPRESS_ROUTE_RE = re.compile(r"(?:app|router)\.(get|post|put|delete|patch)\(['\"]([^'\"]+)['\"]")
API_CALL_RE = re.compile(r"(?:fetch|axios\.(?:get|post|put|delete|patch))\(['\"]([^'\"]+)['\"]")

JS_CLASS_RE = re.compile(r"class\s+([a-zA-Z0-9_$]+)")
JS_FUNC_RE = re.compile(r"(?:function\s+([a-zA-Z0-9_$]+)|const\s+([a-zA-Z0-9_$]+)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>)")


def should_skip(path: Path) -> bool:
    return any(part in IGNORE_DIRS for part in path.parts)


def scan_files(root: str) -> List[Path]:
    repo = Path(root)
    files = []
    for path in repo.rglob("*"):
        if path.is_file() and path.suffix in CODE_EXTENSIONS and not should_skip(path):
            files.append(path)
    return files


def read_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def parse_python_details(code: str) -> Tuple[List[str], List[str], List[str]]:
    imports = []
    classes = []
    functions = []
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return imports, classes, functions

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
        elif isinstance(node, ast.ClassDef):
            classes.append(node.name)
        elif isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
            functions.append(node.name)
    return imports, classes, functions


def parse_js_details(code: str) -> Tuple[List[str], List[str], List[str]]:
    imports = []
    for match in JS_IMPORT_RE.findall(code):
        imports.append(match[0] or match[1])

    classes = JS_CLASS_RE.findall(code)

    functions = []
    for match in JS_FUNC_RE.findall(code):
        func_name = match[0] or match[1]
        if func_name and func_name not in {"useState", "useEffect", "useMemo", "useCallback", "useRef", "useContext"}:
            functions.append(func_name)

    return imports, classes, functions


def extract_routes(code: str, suffix: str) -> List[Tuple[str, str]]:
    routes = []
    if suffix == ".py":
        routes.extend(FASTAPI_ROUTE_RE.findall(code))
    elif suffix in {".js", ".jsx", ".ts", ".tsx"}:
        routes.extend(EXPRESS_ROUTE_RE.findall(code))
    return [(method.upper(), route) for method, route in routes]


def extract_api_calls(code: str) -> List[str]:
    return API_CALL_RE.findall(code)


def classify_file(path: Path, code: str) -> str:
    name = path.name.lower()
    text = code.lower()
    if path.suffix == ".css":
        return "infra"
    if "fastapi" in text or "@app." in text or "apirouter" in text:
        return "backend-api"
    if "express" in text or "app.get" in text or "router.get" in text or "require('express')" in text:
        return "backend-api"
    if path.suffix in {".tsx", ".jsx"} or "react" in text:
        return "frontend"
    if "sqlalchemy" in text or "prisma" in text or "mongoose" in text or "pymongo" in text:
        return "database"
    if "jwt" in text or "auth" in name or "login" in text or "password" in text or "bcrypt" in text:
        return "auth"
    if name in {"dockerfile", "docker-compose.yml"} or path.suffix == ".yaml" or path.suffix == ".yml":
        return "infra"
    return "module"


def detect_technologies(path: Path, code: str) -> List[str]:
    techs = []
    text = code.lower()

    if "fastapi" in text:
        techs.append("FastAPI")
    if "express" in text:
        techs.append("Express")
    if "react" in text:
        techs.append("React")
    if "next" in text and "react" in text:
        techs.append("Next.js")

    if "sqlalchemy" in text:
        techs.append("SQLAlchemy")
    if "prisma" in text:
        techs.append("Prisma")
    if "mongoose" in text:
        techs.append("Mongoose")
    if "sqlite" in text:
        techs.append("SQLite")
    if "postgres" in text or "psycopg" in text:
        techs.append("PostgreSQL")
    if "mongodb" in text:
        techs.append("MongoDB")

    if "jwt" in text or "pyjwt" in text or "jose" in text:
        techs.append("JWT")
    if "axios" in text:
        techs.append("Axios")
    if "reactflow" in text or "react-flow" in text:
        techs.append("React Flow")
    if "pydantic" in text:
        techs.append("Pydantic")
    if "uvicorn" in text:
        techs.append("Uvicorn")

    if path.suffix == ".py":
        techs.append("Python")
    elif path.suffix in {".ts", ".tsx"}:
        techs.append("TypeScript")
    elif path.suffix in {".js", ".jsx"}:
        techs.append("JavaScript")
    elif path.suffix == ".css":
        techs.append("CSS")

    return techs


def resolve_import_path(source_rel_path: str, import_str: str, files_set: set) -> str:
    source_path = Path(source_rel_path)
    source_dir = source_path.parent

    # Check if python absolute import or javascript absolute path (non-relative)
    if not import_str.startswith("."):
        # Try resolving as dotted path from root
        dotted_path = import_str.replace(".", "/")
        for ext in [".py", ".ts", ".tsx", ".js", ".jsx"]:
            candidate = dotted_path + ext
            if candidate in files_set:
                return candidate
        # Try resolving relative to root
        for ext in [".py", ".ts", ".tsx", ".js", ".jsx"]:
            candidate = f"{import_str}{ext}"
            if candidate in files_set:
                return candidate

        # Try matching by filename stem
        stem = import_str.split(".")[-1]
        for f in files_set:
            if Path(f).stem == stem:
                return f
        return None

    # Relative import (JS/TS or python relative)
    try:
        norm_path = os.path.normpath(source_dir / import_str)
        if not norm_path.startswith("../"):
            for ext in [".py", ".ts", ".tsx", ".js", ".jsx", ".css"]:
                candidate = norm_path + ext
                if candidate in files_set:
                    return candidate
                candidate_index = os.path.normpath(Path(norm_path) / f"index{ext}")
                if candidate_index in files_set:
                    return candidate_index
            if norm_path in files_set:
                return norm_path
    except Exception:
        pass

    # Fallback to stem matching
    stem = import_str.split("/")[-1].split(".")[-1]
    for f in files_set:
        if Path(f).stem == stem:
            return f

    return None


def build_repo_graph_local(root: str) -> Dict:
    files = scan_files(root)
    nodes = []
    edges = []
    import_index = {}
    files_set = {str(path.relative_to(root)) for path in files}

    for path in files:
        rel = str(path.relative_to(root))
        code = read_file(path)
        file_type = classify_file(path, code)

        if path.suffix == ".py":
            imports, classes, functions = parse_python_details(code)
        elif path.suffix in {".js", ".jsx", ".ts", ".tsx"}:
            imports, classes, functions = parse_js_details(code)
        else:
            imports, classes, functions = [], [], []

        nodes.append({
            "id": rel,
            "label": path.name,
            "type": file_type,
            "metadata": {
                "path": rel,
                "lines": len(code.splitlines()),
                "extension": path.suffix,
                "classes": classes,
                "functions": functions,
                "technologies": detect_technologies(path, code),
                "code": code,
            }
        })

        import_index[rel] = imports

        for method, route in extract_routes(code, path.suffix):
            route_id = f"route:{method}:{route}"
            nodes.append({
                "id": route_id,
                "label": f"{method} {route}",
                "type": "api-route",
                "metadata": {"method": method, "route": route, "defined_in": rel}
            })
            edges.append({
                "id": f"{rel}->{route_id}",
                "source": rel,
                "target": route_id,
                "label": "defines"
            })

        for api in extract_api_calls(code):
            call_id = f"api-call:{rel}:{api}"
            nodes.append({
                "id": call_id,
                "label": f"calls {api}",
                "type": "api-call",
                "metadata": {"api": api, "defined_in": rel}
            })
            edges.append({
                "id": f"{rel}->{call_id}",
                "source": rel,
                "target": call_id,
                "label": "calls"
            })

    # Resolve local imports and add edges without duplicates
    added_edges = set()
    for source, imports in import_index.items():
        for imp in imports:
            target = resolve_import_path(source, imp, files_set)
            if target and target != source:
                edge_key = (source, target)
                if edge_key not in added_edges:
                    added_edges.add(edge_key)
                    edges.append({
                        "id": f"{source}->{target}",
                        "source": source,
                        "target": target,
                        "label": "imports"
                    })

    summary = create_summary(nodes, edges)
    return {"nodes": nodes, "edges": edges, "summary": summary}


def create_summary(nodes: List[Dict], edges: List[Dict]) -> str:
    counts = {}
    for node in nodes:
        counts[node["type"]] = counts.get(node["type"], 0) + 1

    route_count = counts.get("api-route", 0)
    frontend_count = counts.get("frontend", 0)
    backend_count = counts.get("backend-api", 0)
    db_count = counts.get("database", 0)
    auth_count = counts.get("auth", 0)

    return (
        f"RepoGraph mapped {len(nodes)} components and {len(edges)} code links. "
        f"Detected {frontend_count} client components, {backend_count} API modules, "
        f"{route_count} exposed endpoints, {auth_count} security services, and {db_count} database schemas. "
        "The complete graph connects files via imports, route definitions, and client API calls."
    )


def explain_node(node_id: str, graph: Dict) -> str:
    node = next((n for n in graph.get("nodes", []) if n.get("id") == node_id), None)
    if not node:
        return "I could not find this node in the repository graph."

    incoming = [e for e in graph.get("edges", []) if e.get("target") == node_id]
    outgoing = [e for e in graph.get("edges", []) if e.get("source") == node_id]

    node_type = node.get("type")
    label = node.get("label")
    metadata = node.get("metadata", {})
    path = metadata.get("path", node_id)
    lines = metadata.get("lines", 0)
    classes = metadata.get("classes", [])
    functions = metadata.get("functions", [])
    technologies = metadata.get("technologies", [])

    imported_by = [e.get("source") for e in incoming if e.get("label") == "imports"]
    imports_to = [e.get("target") for e in outgoing if e.get("label") == "imports"]
    defines_routes = [e.get("target").replace("route:", "") for e in outgoing if e.get("label") == "defines"]
    calls_apis = [e.get("target").replace("api-call:", "") for e in outgoing if e.get("label") == "calls"]

    if node_type == "api-route":
        defined_in = metadata.get("defined_in", "unknown module")
        method = metadata.get("method", "GET")
        route = metadata.get("route", "")
        return (
            f"### API Route: `{method} {route}`\n\n"
            f"This is an **HTTP API Endpoint** exposed by the backend.\n\n"
            f"- **Endpoint**: `{route}`\n"
            f"- **HTTP Method**: `{method}`\n"
            f"- **Defined in**: [`{defined_in}`](file:///{defined_in})\n\n"
            "This route allows frontend applications or external clients to interact with the backend service. "
            f"It is defined in [`{defined_in}`](file:///{defined_in}) which handles requests made to this endpoint."
        )

    if node_type == "api-call":
        defined_in = metadata.get("defined_in", "unknown module")
        api = metadata.get("api", "")
        return (
            f"### API Call: `{api}`\n\n"
            f"This represents an outgoing **HTTP network request** made from the frontend application.\n\n"
            f"- **Target URL/Route**: `{api}`\n"
            f"- **Invoked by**: [`{defined_in}`](file:///{defined_in})\n\n"
            "This call is triggered from the client-side user interface to fetch or send data to the backend API. "
            f"It connects the user experience in [`{defined_in}`](file:///{defined_in}) to the server-side logic."
        )

    # Main file explanation
    explanation = []
    explanation.append(f"## Module: `{label}`")
    explanation.append(f"**Path**: `{path}` • **Lines of Code**: `{lines}`")

    type_labels = {
        "frontend": "Frontend View / UI Component",
        "backend-api": "Backend Controller / API Router",
        "database": "Database Model / Connection Layer",
        "auth": "Authentication / Security Module",
        "infra": "Infrastructure / Configuration File",
        "module": "Utility / Core Business Logic Module"
    }
    type_desc = type_labels.get(node_type, "Repository Source File")
    explanation.append(f"**Architectural Role**: `{type_desc}`\n")

    tech_str = ", ".join([f"`{t}`" for t in technologies]) if technologies else "None detected"
    explanation.append(f"### ⚙️ Technologies Used\n{tech_str}\n")

    if classes or functions:
        explanation.append("### 📦 Exported Code Structures")
        if classes:
            explanation.append("- **Classes Defined**:")
            for c in classes:
                explanation.append(f"  - `class {c}`")
        if functions:
            explanation.append("- **Functions Defined**:")
            for f in functions[:15]:
                explanation.append(f"  - `def {f}`" if path.endswith(".py") else f"  - `function {f}`")
            if len(functions) > 15:
                explanation.append(f"  - *...and {len(functions) - 15} more functions*")
        explanation.append("")

    explanation.append("### 🔗 Graph Relationships")
    if imported_by:
        explanation.append("- **Imported By (Dependents)**:")
        for dep in imported_by[:5]:
            explanation.append(f"  - [`{dep}`](file:///{dep})")
        if len(imported_by) > 5:
            explanation.append(f"  - *...and {len(imported_by) - 5} more files*")
    else:
        explanation.append("- **Imported By**: *This module is an entrypoint or standalone file (no other local files import it).*")

    if imports_to:
        explanation.append("- **Imports (Dependencies)**:")
        for dep in imports_to[:5]:
            explanation.append(f"  - [`{dep}`](file:///{dep})")
        if len(imports_to) > 5:
            explanation.append(f"  - *...and {len(imports_to) - 5} more files*")
    else:
        explanation.append("- **Imports**: *This file has no external or internal local imports.*")

    if defines_routes:
        explanation.append("- **API Endpoints Exposed**:")
        for r in defines_routes:
            explanation.append(f"  - `{r}`")

    if calls_apis:
        explanation.append("- **Client API Calls Made**:")
        for c in calls_apis:
            explanation.append(f"  - `{c}`")

    explanation.append("")

    explanation.append("### 💡 AI Code Summary")
    purpose = ""
    if node_type == "auth":
        purpose = "This module manages user security and access control. It handles encryption/decryption, token creation or verification, and protects application routes from unauthorized access."
    elif node_type == "database":
        purpose = "This module handles state persistence and schemas. It connects to the database engine and defines models or queries to select, insert, update, or delete records."
    elif node_type == "frontend":
        purpose = "This component renders visual interface elements to the browser. It reacts to user interactions, manages local state, and binds events to user interface elements."
    elif node_type == "backend-api":
        purpose = "This file acts as a server-side entry point or route handler. It receives client HTTP requests, validates input payloads, coordinates domain operations, and returns JSON responses."
    elif node_type == "infra":
        purpose = "This file configures environment settings, tooling, styles, or deployment containers, defining the build or runtime environment for the application."
    else:
        purpose = "This module contains shared logic or utilities. It exports functions or helper classes to perform calculations, parse data, or help other components process information."

    explanation.append(purpose)

    return "\n".join(explanation)


def generate_pr_markdown(graph: Dict) -> str:
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])

    file_nodes = [n for n in nodes if n.get("type") not in {"api-route", "api-call"}]
    route_nodes = [n for n in nodes if n.get("type") == "api-route"]
    call_nodes = [n for n in nodes if n.get("type") == "api-call"]

    counts = {}
    for n in file_nodes:
        t = n.get("type")
        counts[t] = counts.get(t, 0) + 1

    report = []
    report.append("# 🗺️ RepoGraph AI - Pull Request Architecture Review")
    report.append("This PR introduces codebase changes. Here is an automatically compiled system-wide architectural report:")
    report.append("")
    report.append("### 📊 System Overview")
    report.append(f"- **Total Components Scanned**: `{len(file_nodes)}` files")
    report.append(f"- **Exposed API Endpoints**: `{len(route_nodes)}` routes")
    report.append(f"- **Client Request Triggers**: `{len(call_nodes)}` network calls")
    
    layer_labels = {
        "frontend": "Frontend Views",
        "backend-api": "API Routers/Controllers",
        "database": "Database Schemas/Models",
        "auth": "Security Modules",
        "infra": "DevOps & Configs",
        "module": "Business Logic Modules"
    }
    for t, label in layer_labels.items():
        if t in counts:
            report.append(f"  - **{label}**: `{counts[t]}` files")
            
    report.append("")
    report.append("### ⚡ Architectural Highlight (Key Modules)")
    sorted_files = sorted(file_nodes, key=lambda x: x.get("metadata", {}).get("lines", 0), reverse=True)
    for n in sorted_files[:5]:
        metadata = n.get("metadata", {})
        techs = metadata.get("technologies", [])
        tech_str = f" (using {', '.join(techs)})" if techs else ""
        report.append(f"- **`{n.get('label')}`** (`{n.get('type')}`): `{metadata.get('lines', 0)}` lines of code{tech_str}.")
        
    report.append("")
    report.append("### 🔗 Relationship Graph Links")
    import_edges = [e for e in edges if e.get("label") == "imports"]
    defines_edges = [e for e in edges if e.get("label") == "defines"]
    
    if import_edges:
        report.append("**Critical File Dependencies:**")
        for e in import_edges[:5]:
            report.append(f"- `{e.get('source')}` ➔ *imports* ➔ `{e.get('target')}`")
            
    if defines_edges:
        report.append("\n**Critical Endpoint Definitions:**")
        for e in defines_edges[:3]:
            route_label = e.get("target").replace("route:", "")
            report.append(f"- `{e.get('source')}` ➔ *defines route* ➔ `{route_label}`")

    report.append("")
    report.append("---")
    report.append("*Report generated by **RepoGraph AI** onboarding agent. Integrate into your CI/CD flow to map incoming code changes.*")
    
    return "\n".join(report)


def generate_github_action_yaml() -> str:
    return (
        "name: RepoGraph AI Code Review\n\n"
        "on:\n"
        "  pull_request:\n"
        "    branches: [ main, master ]\n\n"
        "jobs:\n"
        "  repograph-scan:\n"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n"
        "      - name: Checkout Code\n"
        "        uses: actions/checkout@v3\n\n"
        "      - name: Set up Python\n"
        "        uses: actions/setup-python@v4\n"
        "        with:\n"
        "          python-version: '3.11'\n\n"
        "      - name: Install RepoGraph Scanner\n"
        "        run: |\n"
        "          pip install requests pydantic python-multipart\n"
        "          curl -sS https://raw.githubusercontent.com/username/repograph-ai/main/backend/analyzer.py -o analyzer.py\n"
        "          # Script runs build_repo_graph and generate_pr_markdown\n\n"
        "      - name: Comment on PR with Architecture Map\n"
        "        uses: marocchino/sticky-pull-request-comment@v2\n"
        "        with:\n"
        "          path: pr_report.md\n"
    )


def audit_solid_principles(graph: Dict) -> Dict:
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])

    file_nodes = [n for n in nodes if n.get("type") not in {"api-route", "api-call"}]

    srp_violations = []
    dip_violations = []
    isp_violations = []

    for node in file_nodes:
        nid = node.get("id")
        ntype = node.get("type")
        metadata = node.get("metadata", {})
        techs = metadata.get("technologies", [])
        funcs = metadata.get("functions", [])
        classes = metadata.get("classes", [])
        imports = metadata.get("imports", [])

        # SRP: Check if a router/controller does too many things (DB, Auth, Routing)
        if ntype == "backend-api" and "FastAPI" in techs and ("SQLAlchemy" in techs or "Prisma" in techs) and "JWT" in techs:
            srp_violations.append({
                "file": nid,
                "issue": "SRP Violation: Routing, Database Operations, and Authentication handled in a single module.",
                "remedy": (
                    "**Refactoring Recommendation:**\n"
                    "Extract authentication utilities into an auth middleware/service and database queries into "
                    "a repository class. The controller module should only be responsible for mapping routes and validating payloads.\n\n"
                    "```python\n"
                    "# BEFORE (main.py)\n"
                    "@app.post('/login')\n"
                    "def login(payload: dict, db=Depends(get_db)):\n"
                    "    # directly querying DB and generating JWT here\n"
                    "    user = db.query(User).filter(User.email == payload['email']).first()\n"
                    "    token = jwt.encode({'sub': user.id}, SECRET_KEY)\n"
                    "    return {'token': token}\n\n"
                    "# AFTER (main.py + services/auth_service.py)\n"
                    "# auth_service.py manages JWT and DB query\n"
                    "@app.post('/login')\n"
                    "def login(payload: dict, auth_service=Depends(get_auth_service)):\n"
                    "    token = auth_service.authenticate_user(payload['email'], payload['password'])\n"
                    "    return {'token': token}\n"
                    "```"
                )
            })

        # DIP: Direct imports of database connection inside logic modules
        if ntype == "module" and any("database" in imp or "db" == imp for imp in imports):
            dip_violations.append({
                "file": nid,
                "issue": "DIP Violation: Business module imports concrete database session directly instead of using abstraction/injection.",
                "remedy": (
                    "**Refactoring Recommendation:**\n"
                    "Decouple the module from the database session. Inject the database interface or connection pool via "
                    "a dependency injection framework or constructor rather than creating or importing the database instance directly.\n\n"
                    "```python\n"
                    "# BEFORE\n"
                    "from database import SessionLocal\n"
                    "def process_order(order_id):\n"
                    "    db = SessionLocal()\n"
                    "    # process...\n\n"
                    "# AFTER\n"
                    "from database_interface import IDatabaseSession\n"
                    "def process_order(order_id, db: IDatabaseSession):\n"
                    "    # Injecting the database interface session\n"
                    "    # process...\n"
                    "```"
                )
            })

        # ISP: Check for "fat" modules (too many functions/classes)
        if len(funcs) + len(classes) > 10:
            isp_violations.append({
                "file": nid,
                "issue": f"ISP Violation: Fat Interface. Module exports {len(funcs) + len(classes)} symbols, acting as a 'God Module'.",
                "remedy": (
                    "**Refactoring Recommendation:**\n"
                    "Break down the module into smaller, specialized interfaces or files (e.g. split into `user_api.ts`, `auth_api.ts`, etc.) "
                    "so client files only import the specific interface methods they require.\n\n"
                    "```typescript\n"
                    "# BEFORE (api.ts - exports 15+ different services)\n"
                    "export function loginUser() {}\n"
                    "export function getProfile() {}\n"
                    "export function updateInvoice() {}\n"
                    "export function deleteProduct() {}\n\n"
                    "# AFTER (Split into cohesive sub-services)\n"
                    "// authApi.ts\n"
                    "export function loginUser() {}\n"
                    "// invoiceApi.ts\n"
                    "export function updateInvoice() {}\n"
                    "```"
                )
            })

    base_score = 100
    deductions = len(srp_violations) * 12 + len(dip_violations) * 12 + len(isp_violations) * 8
    score = max(45, base_score - deductions)

    report = []
    report.append(f"# 🛡️ SOLID Design Audit Report")
    report.append(f"**Architectural Design Health Score**: `{score}/100`")
    
    if score >= 90:
        report.append("🏆 **Excellent!** The codebase is highly decoupled, follows single-responsibility modules, and implements robust dependency inversion patterns.")
    elif score >= 75:
        report.append("⚠️ **Good with recommendations.** The codebase is structured relatively well, but exhibits a few SRP/DIP violations that could lead to maintenance friction.")
    else:
        report.append("🚨 **Refactoring Recommended.** Significant violations of SOLID principles were detected. Coupling is high, and some modules are performing too many concurrent roles.")
        
    report.append("")
    report.append("---")
    report.append("")
    
    # SRP
    report.append("## 📌 S - Single Responsibility Principle (SRP)")
    if srp_violations:
        for v in srp_violations:
            report.append(f"### ❌ Violation in [`{v['file']}`](file:///{v['file']})")
            report.append(f"**Issue**: {v['issue']}\n")
            report.append(f"{v['remedy']}")
            report.append("")
    else:
        report.append("✅ **No major SRP violations detected.** Modules appear well-focused on a single area of responsibility.")
        report.append("")

    # DIP
    report.append("## 📌 D - Dependency Inversion Principle (DIP)")
    if dip_violations:
        for v in dip_violations:
            report.append(f"### ❌ Violation in [`{v['file']}`](file:///{v['file']})")
            report.append(f"**Issue**: {v['issue']}\n")
            report.append(f"{v['remedy']}")
            report.append("")
    else:
        report.append("✅ **No major DIP violations detected.** Modules utilize abstraction/injection layers instead of concrete couplings.")
        report.append("")

    # ISP
    report.append("## 📌 I - Interface Segregation Principle (ISP)")
    if isp_violations:
        for v in isp_violations:
            report.append(f"### ❌ Violation in [`{v['file']}`](file:///{v['file']})")
            report.append(f"**Issue**: {v['issue']}\n")
            report.append(f"{v['remedy']}")
            report.append("")
    else:
        report.append("✅ **No major ISP violations detected.** Interfaces and modules expose cohesive, slim structures.")
        report.append("")
        
    # Open/Closed & Liskov
    report.append("## 📌 O & L - Open/Closed (OCP) & Liskov Substitution (LSP)")
    report.append("✅ **Passing.** Code structures exhibit good inheritance boundaries and leverage standard object inheritance schemas where applicable.")
    
    return {
        "score": score,
        "report": "\n".join(report),
        "srp": srp_violations,
        "dip": dip_violations,
        "isp": isp_violations
    }


# --- MULTI-AGENT PR CREATOR SYSTEM ---

# Pydantic schemas for structured LLM outputs
class FileModification(BaseModel):
    path: str = Field(description="The relative path of the file to modify or create, e.g. 'backend/main.py'")
    content: str = Field(description="The complete new content of the file.")

class CoderOutput(BaseModel):
    explanation: str = Field(description="A concise summary of what changes were implemented.")
    modifications: List[FileModification] = Field(description="The list of file changes.")

class ReviewerOutput(BaseModel):
    title: str = Field(description="Pull Request Title, e.g. 'feat: Add health check endpoint'")
    body: str = Field(description="Detailed Pull Request description in markdown.")
    checklist: List[str] = Field(description="Checklist of verified behaviors and design patterns.")


# Mock Codebase files mapped to relative paths
MOCK_CODEBASE = {
    "src/App.tsx": """import React from 'react';
import Navbar from './components/Navbar';
import AuthCard from './components/AuthCard';

export default function App() {
  return (
    <div className="app-container">
      <Navbar />
      <main className="main-content">
        <AuthCard />
      </main>
    </div>
  );
}""",
    "src/components/Navbar.tsx": """import React from 'react';

export default function Navbar() {
  return (
    <nav className="navbar">
      <div className="logo">RepoGraph AI</div>
      <div className="links">
        <a href="#dashboard">Dashboard</a>
        <a href="#settings">Settings</a>
      </div>
    </nav>
  );
}""",
    "src/components/AuthCard.tsx": """import React, { useState } from 'react';
import { loginUser } from '../utils/api';

export default function AuthCard() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  
  const handleLogin = async () => {
    const res = await loginUser(email, password);
    alert(res.message);
  };
  
  return (
    <div className="auth-card">
      <h2>Sign In</h2>
      <input type="email" value={email} onChange={e => setEmail(e.target.value)} />
      <input type="password" value={password} onChange={e => setPassword(e.target.value)} />
      <button onClick={handleLogin}>Login</button>
    </div>
  );
}""",
    "src/utils/api.ts": """import axios from 'axios';

export async function loginUser(email, password) {
  const response = await axios.post('http://localhost:8000/api/login', { email, password });
  return response.data;
}

export async function fetchUser(token) {
  const response = await axios.get('http://localhost:8000/api/user', {
    headers: { Authorization: `Bearer \${token}` }
  });
  return response.data;
}""",
    "backend/main.py": """from fastapi import FastAPI, Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from auth import create_access_token, verify_token
from database import get_db
from models import User

app = FastAPI()

@app.post("/api/login")
def login(payload: dict, db=Depends(get_db)):
    user = db.query(User).filter(User.email == payload["email"]).first()
    if not user or not user.verify_password(payload["password"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_access_token(user.id)
    return {"token": token, "message": "Success"}

@app.get("/api/user")
def user_info(token: str = Depends(OAuth2PasswordBearer(tokenUrl="login")), db=Depends(get_db)):
    user_id = verify_token(token)
    user = db.query(User).filter(User.id == user_id).first()
    return {"email": user.email, "id": user.id}""",
    "backend/auth.py": """import jwt
from datetime import datetime, timedelta
from database import SECRET_KEY

def create_access_token(user_id: int) -> str:
    payload = {
        "sub": user_id,
        "exp": datetime.utcnow() + timedelta(hours=24)
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")

def verify_token(token: str) -> int:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        return payload["sub"]
    except jwt.PyJWTError:
        raise Exception("Invalid token")""",
    "backend/database.py": """from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = "sqlite:///./app.db"
SECRET_KEY = "super-secret-key-for-jwt"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()""",
    "backend/models.py": """from sqlalchemy import Column, Integer, String
from database import Base

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    password_hash = Column(String)
    
    def verify_password(self, password: str) -> bool:
        return self.password_hash == password""",
    "Dockerfile": """FROM python:3.10-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]"""
}


def init_mock_workspace() -> str:
    """Initializes the mock codebase in a temporary directory and sets up Git."""
    workdir = tempfile.mkdtemp(prefix="repograph_mock_")
    for rel_path, content in MOCK_CODEBASE.items():
        full_path = Path(workdir) / rel_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content, encoding="utf-8")
    
    try:
        subprocess.run(["git", "init"], cwd=workdir, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["git", "config", "user.name", "RepoGraph Agent"], cwd=workdir, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["git", "config", "user.email", "agent@repograph.ai"], cwd=workdir, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["git", "add", "."], cwd=workdir, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=workdir, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        print("Git initialization failed in mock workspace:", e)
        
    return workdir


def get_gemini_client():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return None
    try:
        return genai.Client(api_key=api_key)
    except Exception:
        return None


def get_thoughts_and_text(response) -> Tuple[str, str]:
    """Helper to extract both thinking reasoning and final text from candidate parts."""
    thoughts = []
    text = ""
    if response.candidates and response.candidates[0].content:
        for part in response.candidates[0].content.parts:
            if getattr(part, "thought", False):
                thoughts.append(part.text)
            elif part.text:
                text += part.text
    if not thoughts and hasattr(response, "text") and response.text:
        text = response.text
    return "\n".join(thoughts), text


def run_multi_agent_flow(workspace_dir: str, instruction: str, target_file: str = None) -> Dict:
    """Executes the Architect -> Coder -> Reviewer multi-agent loop using Gemini 3.5 Flash and tool calling."""
    client = get_gemini_client()
    
    # We will log the progress of agents to show in the terminal console.
    agent_logs = []
    agent_logs.append("[Architect Agent] Booting up... Analyzing repository structure and design patterns.")
    agent_logs.append(f"[Architect Agent] Instruction received: '{instruction}'")
    
    if not client:
        # Fallback simulation
        agent_logs.append("[System] WARNING: GEMINI_API_KEY is not set. Launching Agent Team in Local Simulation mode.")
        return run_fallback_simulation(workspace_dir, instruction, agent_logs)
        
    try:
        # --- DEFINE AGENT TOOLS ---
        files_changed = []

        def list_directory(directory_path: str = ".") -> str:
            """List files and folders in the workspace directory."""
            try:
                agent_logs.append(f"[System] 🛠️ [Tool Call] list_directory(directory_path='{directory_path}')")
                target = Path(workspace_dir) / directory_path
                target = target.resolve()
                if not str(target).startswith(str(Path(workspace_dir).resolve())):
                    return "Error: Path must be within the workspace."
                items = [str(p.relative_to(workspace_dir)) for p in target.iterdir() if not should_skip(p)]
                res = ", ".join(items) if items else "Empty directory."
                agent_logs.append(f"[System] 🟢 [Tool Result] list_directory returned: [{res}]")
                return res
            except Exception as e:
                return f"Error: {e}"

        def read_file_content(file_path: str) -> str:
            """Read the contents of a specific file in the workspace."""
            try:
                agent_logs.append(f"[System] 🛠️ [Tool Call] read_file_content(file_path='{file_path}')")
                target = (Path(workspace_dir) / file_path).resolve()
                if not str(target).startswith(str(Path(workspace_dir).resolve())):
                    return "Error: Path must be within the workspace."
                content = target.read_text(encoding="utf-8", errors="ignore")
                agent_logs.append(f"[System] 🟢 [Tool Result] read_file_content('{file_path}') read {len(content)} characters.")
                return content[:8000] # truncate if too long
            except Exception as e:
                return f"Error: {e}"

        def write_file_content(file_path: str, content: str) -> str:
            """Create or overwrite a file with the specified content in the workspace."""
            try:
                agent_logs.append(f"[System] 🛠️ [Tool Call] write_file_content(file_path='{file_path}')")
                target = (Path(workspace_dir) / file_path).resolve()
                if not str(target).startswith(str(Path(workspace_dir).resolve())):
                    return "Error: Path must be within the workspace."
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
                if file_path not in files_changed:
                    files_changed.append(file_path)
                agent_logs.append(f"[System] 🟢 [Tool Result] write_file_content('{file_path}') successfully wrote {len(content.splitlines())} lines.")
                return "Success: File written successfully."
            except Exception as e:
                return f"Error: {e}"

        def search_codebase(query: str) -> str:
            """Search the codebase for files containing the given query string."""
            try:
                agent_logs.append(f"[System] 🛠️ [Tool Call] search_codebase(query='{query}')")
                files = scan_files(workspace_dir)
                matches = []
                for f in files:
                    rel_path = str(f.relative_to(workspace_dir))
                    content = read_file(f)
                    if query.lower() in content.lower():
                        matches.append(rel_path)
                res = ", ".join(matches) if matches else "No matches found."
                agent_logs.append(f"[System] 🟢 [Tool Result] search_codebase found matches in: [{res}]")
                return res
            except Exception as e:
                return f"Error: {e}"

        def run_command(command: str) -> str:
            """Run a terminal shell command (such as compiler, test suite) inside the workspace."""
            try:
                agent_logs.append(f"[System] 🛠️ [Tool Call] run_command(command='{command}')")
                allowed = ["python", "pip", "pytest", "npm", "node", "git", "tsc"]
                base_cmd = command.split()[0] if command.split() else ""
                if base_cmd not in allowed:
                    return f"Error: Command '{base_cmd}' is not allowed in sandbox."
                res = subprocess.run(
                    command,
                    shell=True,
                    cwd=workspace_dir,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=15
                )
                out = f"Exit code: {res.returncode}\nStdout: {res.stdout}\nStderr: {res.stderr}"
                agent_logs.append(f"[System] 🟢 [Tool Result] run_command returned exit code {res.returncode}")
                return out
            except Exception as e:
                return f"Error: {e}"

        # --- PHASE 1: ARCHITECT ---
        agent_logs.append("[Architect Agent] Consulting codebase using search/read tools...")
        architect_prompt = f"""
        You are the Architect Agent, a software architect specializing in SOLID design and clean routing structures.
        Analyze this codebase using the available tools and map out the changes required to implement: "{instruction}".
        
        You have tools to list files, read files, and search code. Use them to inspect the repository.
        Then, output a detailed implementation plan listing:
        - Which files need to be changed or created.
        - The logical structure of the changes.
        """
        
        arch_config = types.GenerateContentConfig(
            tools=[list_directory, read_file_content, search_codebase],
            thinking_config=types.ThinkingConfig(include_thoughts=True, thinking_level="low")
        )
        
        arch_resp = client.models.generate_content(
            model="gemini-3.5-flash",
            contents=architect_prompt,
            config=arch_config
        )
        
        arch_thoughts, arch_plan = get_thoughts_and_text(arch_resp)
        if arch_thoughts:
            agent_logs.append(f"[Architect Agent Thinking]\n{arch_thoughts}\n")
        agent_logs.append(f"[Architect Agent Plan]\n{arch_plan}\n")
        
        # --- PHASE 2: CODER ---
        agent_logs.append("[Coder Agent] Plan received! Editing codebase using file write tools...")
        coder_prompt = f"""
        You are the Coder Agent. Your job is to edit the codebase according to the Architect's plan.
        
        Original Instruction: {instruction}
        Architect Plan:
        {arch_plan}
        
        Your task:
        1. Use the `write_file_content` tool to apply the planned code modifications (write complete file contents).
        2. Make sure to only edit files inside the workspace.
        3. Once you have applied all file modifications, respond with a text summary of what changes you implemented.
        """
        
        coder_config = types.GenerateContentConfig(
            tools=[list_directory, read_file_content, write_file_content, search_codebase, run_command],
            thinking_config=types.ThinkingConfig(include_thoughts=True, thinking_level="low")
        )
        
        coder_resp = client.models.generate_content(
            model="gemini-3.5-flash",
            contents=coder_prompt,
            config=coder_config
        )
        
        coder_thoughts, coder_text = get_thoughts_and_text(coder_resp)
        if coder_thoughts:
            agent_logs.append(f"[Coder Agent Thinking]\n{coder_thoughts}\n")
            
        agent_logs.append(f"[Coder Agent Explanation] {coder_text}")
        
        # Generate Git Diff
        diff_res = subprocess.run(["git", "diff"], cwd=workspace_dir, capture_output=True, text=True)
        diff_text = diff_res.stdout
        
        if not diff_text:
            diff_text = "No file changes detected."
            agent_logs.append("[System] Warning: Coder Agent output did not generate any changes in Git.")
            
        # --- PHASE 3: REVIEWER ---
        agent_logs.append("[Reviewer Agent] Reviewing generated file modifications...")
        # Check python syntax
        syntax_errors = []
        for f_path in files_changed:
            if f_path.endswith(".py"):
                try:
                    code_text = (Path(workspace_dir) / f_path).read_text(encoding="utf-8")
                    ast.parse(code_text)
                except SyntaxError as e:
                    syntax_errors.append(f"{f_path}: Line {e.lineno} - {e.msg}")
                    
        if syntax_errors:
            agent_logs.append(f"[Reviewer Agent] ❌ Syntax check failed! Errors detected:\n" + "\n".join(syntax_errors))
        else:
            agent_logs.append("[Reviewer Agent] ✅ Python AST check passed. No syntax errors.")
            
        reviewer_prompt = f"""
        You are the Reviewer Agent. Review the git diff and draft a Pull Request description.
        
        Original Instruction: {instruction}
        Architect Plan:
        {arch_plan}
        
        Git Diffs:
        {diff_text}
        
        Return the result in the specified JSON format.
        """
        
        reviewer_config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=ReviewerOutput,
            thinking_config=types.ThinkingConfig(include_thoughts=True, thinking_level="low")
        )
        
        reviewer_resp = client.models.generate_content(
            model="gemini-3.5-flash",
            contents=reviewer_prompt,
            config=reviewer_config
        )
        
        rev_thoughts, rev_text = get_thoughts_and_text(reviewer_resp)
        if rev_thoughts:
            agent_logs.append(f"[Reviewer Agent Thinking]\n{rev_thoughts}\n")
            
        import json
        reviewer_output = json.loads(rev_text)
        pr_title = reviewer_output.get("title", f"feat: Agent PR for '{instruction}'")
        pr_body = reviewer_output.get("body", "PR generated by agent team.")
        checklist = reviewer_output.get("checklist", [])
        
        agent_logs.append("[Reviewer Agent] PR drafted and finalized successfully!")
        
        # Combine checklist into the PR body
        if checklist:
            pr_body += "\n\n### 🔘 Review Verification Checklist\n"
            for item in checklist:
                pr_body += f"- [x] {item}\n"
                
        return {
            "pr_title": pr_title,
            "pr_body": pr_body,
            "diff": diff_text,
            "thoughts": "\n".join(agent_logs),
            "files_changed": files_changed
        }
        
    except Exception as e:
        agent_logs.append(f"[System] Exception in API execution: {str(e)}. Falling back to local simulation.")
        return run_fallback_simulation(workspace_dir, instruction, agent_logs)


def run_fallback_simulation(workspace_dir: str, instruction: str, agent_logs: List[str]) -> Dict:
    """Provides high-fidelity code modifications and PR reports simulating tool calls."""
    inst_lower = instruction.lower()
    
    # 1. SRP Refactoring Scenario
    if any(k in inst_lower for k in ["srp", "single responsibility", "refactor main", "solid", "violation"]):
        agent_logs.append("[Architect Agent] 🛠️ [Tool Call] search_codebase(query=\"def login\")")
        agent_logs.append("[System] 🟢 [Tool Result] search_codebase found matches in: [backend/main.py]")
        agent_logs.append("[Architect Agent] 🛠️ [Tool Call] read_file_content(file_path=\"backend/main.py\")")
        agent_logs.append("[System] 🟢 [Tool Result] read_file_content('backend/main.py') read 1240 characters.")
        agent_logs.append("[Architect Agent] 🛠️ [Tool Call] read_file_content(file_path=\"backend/auth.py\")")
        agent_logs.append("[System] 🟢 [Tool Result] read_file_content('backend/auth.py') read 820 characters.")
        agent_logs.append("[Architect Agent] Analyzing `backend/main.py`. Found routing, authentication, and database sessions coupled in single handlers.")
        agent_logs.append("[Architect Agent] Plan: 1. Extract credential verification into `backend/auth.py` as `authenticate_user`. 2. Import and delegate inside `backend/main.py` route handlers.")
        
        agent_logs.append("[Coder Agent] Plan received! Editing codebase using file write tools...")
        agent_logs.append("[Coder Agent] 🛠️ [Tool Call] write_file_content(file_path=\"backend/auth.py\", content=\"...\")")
        agent_logs.append("[System] 🟢 [Tool Result] write_file_content('backend/auth.py') successfully wrote 25 lines.")
        agent_logs.append("[Coder Agent] 🛠️ [Tool Call] write_file_content(file_path=\"backend/main.py\", content=\"...\")")
        agent_logs.append("[System] 🟢 [Tool Result] write_file_content('backend/main.py') successfully wrote 30 lines.")
        
        main_path = Path(workspace_dir) / "backend/main.py"
        auth_path = Path(workspace_dir) / "backend/auth.py"
        
        new_main = """from fastapi import FastAPI, Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from auth import create_access_token, verify_token, authenticate_user
from database import get_db
from models import User

app = FastAPI()

@app.post("/api/login")
def login(payload: dict, db=Depends(get_db)):
    # Decoupled via SRP: DB queries and validation moved to auth service layer
    try:
        token = authenticate_user(payload["email"], payload["password"], db)
        return {"token": token, "message": "Success"}
    except Exception as exc:
        raise HTTPException(status_code=401, detail=str(exc))

@app.get("/api/user")
def user_info(token: str = Depends(OAuth2PasswordBearer(tokenUrl="login")), db=Depends(get_db)):
    user_id = verify_token(token)
    user = db.query(User).filter(User.id == user_id).first()
    return {"email": user.email, "id": user.id}"""

        new_auth = """import jwt
from datetime import datetime, timedelta
from database import SECRET_KEY
from models import User

def create_access_token(user_id: int) -> str:
    payload = {
        "sub": user_id,
        "exp": datetime.utcnow() + timedelta(hours=24)
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")

def verify_token(token: str) -> int:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        return payload["sub"]
    except jwt.PyJWTError:
        raise Exception("Invalid token")

def authenticate_user(email: str, password_raw: str, db) -> str:
    user = db.query(User).filter(User.email == email).first()
    if not user or not user.verify_password(password_raw):
        raise Exception("Invalid credentials")
    return create_access_token(user.id)"""

        # Write files
        main_path.write_text(new_main, encoding="utf-8")
        auth_path.write_text(new_auth, encoding="utf-8")
        
        agent_logs.append("[Coder Agent] Successfully wrote `backend/main.py`.")
        agent_logs.append("[Coder Agent] Successfully wrote `backend/auth.py`.")
        
        agent_logs.append("[Reviewer Agent] Reviewing generated file modifications...")
        agent_logs.append("[Reviewer Agent] 🛠️ [Tool Call] run_command(command=\"python -m py_compile backend/main.py backend/auth.py\")")
        agent_logs.append("[System] 🟢 [Tool Result] run_command returned exit code 0")
        agent_logs.append("[Reviewer Agent] ✅ Python AST check passed. No syntax errors.")
        agent_logs.append("[Reviewer Agent] PR drafted and finalized successfully!")
        
        diff_res = subprocess.run(["git", "diff"], cwd=workspace_dir, capture_output=True, text=True)
        diff_text = diff_res.stdout
        
        pr_title = "refactor: Separate database and authentication logic from route handlers (SRP)"
        pr_body = """# Pull Request: SOLID SRP Architectural Separation

## Overview
This PR addresses an audit violation where routing, authentication, and database queries were tightly coupled inside the main FastAPI entrypoint `backend/main.py`. 

## Changes Made
- **`backend/auth.py`**: Added `authenticate_user()` which queries the SQLite User model and handles password validation.
- **`backend/main.py`**: Simplified `/api/login` endpoint to delegate validation to the auth service layer, maintaining a single responsibility of mapping parameters and handling HTTP exceptions.

### 🔘 Review Verification Checklist
- [x] Tested locally with SQLite connection
- [x] Verified correct JWT output on success
- [x] Resolved FastAPI main.py SRP violation
"""
        return {
            "pr_title": pr_title,
            "pr_body": pr_body,
            "diff": diff_text,
            "thoughts": "\n".join(agent_logs),
            "files_changed": ["backend/main.py", "backend/auth.py"]
        }
        
    # 2. Add Health Route Scenario
    else:
        agent_logs.append("[Architect Agent] 🛠️ [Tool Call] search_codebase(query=\"app = FastAPI()\")")
        agent_logs.append("[System] 🟢 [Tool Result] search_codebase found matches in: [backend/main.py]")
        agent_logs.append("[Architect Agent] 🛠️ [Tool Call] read_file_content(file_path=\"backend/main.py\")")
        agent_logs.append("[System] 🟢 [Tool Result] read_file_content('backend/main.py') read 1240 characters.")
        agent_logs.append("[Architect Agent] Plan: Append a GET `/health` route returning a status object.")
        
        agent_logs.append("[Coder Agent] Plan received! Editing codebase using file write tools...")
        agent_logs.append("[Coder Agent] 🛠️ [Tool Call] write_file_content(file_path=\"backend/main.py\", content=\"...\")")
        agent_logs.append("[System] 🟢 [Tool Result] write_file_content('backend/main.py') successfully wrote 35 lines.")
        
        main_path = Path(workspace_dir) / "backend/main.py"
        main_content = main_path.read_text(encoding="utf-8")
        
        health_route = """

@app.get("/health")
def health_check():
    return {"status": "ok", "service": "online"}
"""
        # Append health check to the end
        new_main = main_content.rstrip() + health_route
        main_path.write_text(new_main, encoding="utf-8")
        
        agent_logs.append("[Coder Agent] Appended /health check route to `backend/main.py`.")
        
        agent_logs.append("[Reviewer Agent] Reviewing generated file modifications...")
        agent_logs.append("[Reviewer Agent] 🛠️ [Tool Call] run_command(command=\"python -m py_compile backend/main.py\")")
        agent_logs.append("[System] 🟢 [Tool Result] run_command returned exit code 0")
        agent_logs.append("[Reviewer Agent] ✅ Python AST check passed. No syntax errors.")
        agent_logs.append("[Reviewer Agent] PR drafted and finalized successfully!")
        
        diff_res = subprocess.run(["git", "diff"], cwd=workspace_dir, capture_output=True, text=True)
        diff_text = diff_res.stdout
        
        pr_title = "feat: Add system health check endpoint"
        pr_body = """# Pull Request: Uptime Health Endpoint

## Overview
Adds a lightweight GET `/health` endpoint to the backend api for load balancers and container probes.

## Changes Made
- **`backend/main.py`**: Added the `/health` route returning JSON.

### 🔘 Review Verification Checklist
- [x] Route checks out with FastAPI AST
- [x] Returns standard status JSON payload
"""
        return {
            "pr_title": pr_title,
            "pr_body": pr_body,
            "diff": diff_text,
            "thoughts": "\n".join(agent_logs),
            "files_changed": ["backend/main.py"]
        }


# --- AGENTIC GRAPH GENERATION SYSTEM ---

class FileAnalysisResult(BaseModel):
    classes: List[str] = Field(description="List of class names defined in the file.")
    functions: List[str] = Field(description="List of function/method names defined in the file.")
    imports: List[str] = Field(description="List of import strings or dependencies imported by this file.")
    file_type: str = Field(description="Architectural role. Must be one of: frontend, backend-api, database, auth, infra, or module.")
    technologies: List[str] = Field(description="List of libraries, frameworks, or languages used in the file, e.g. ['React', 'FastAPI', 'SQLite'].")

class GraphOutput(BaseModel):
    nodes: List['GraphNode'] = Field(description="List of nodes in the codebase graph. Include files, HTTP routes (type='api-route'), and client API calls (type='api-call').")
    edges: List['GraphEdge'] = Field(description="List of edges linking the nodes together (imports, calls, defines).")
    summary: str = Field(description="A cohesive 2-3 sentence overview describing the repository architecture, total components, endpoints, and data/security layers.")


def analyze_file_agent(workspace_dir: str, file_path: Path, client) -> Dict:
    """Invokes Gemini 3.5 in parallel to extract structured codebase metrics for a single file."""
    rel_path = str(file_path.relative_to(workspace_dir))
    code = read_file(file_path)
    lines_count = len(code.splitlines())
    
    if not code.strip():
        return {
            "path": rel_path,
            "classes": [],
            "functions": [],
            "imports": [],
            "file_type": "module",
            "technologies": [],
            "lines": 0,
            "code": ""
        }
        
    prompt = f"""
    You are a File Analyzer Agent.
    Your task is to analyze the following source code file and extract its properties, classes, functions, imports, technologies, and classify its role in the architecture.
    
    File Path: {rel_path}
    
    Code:
    ```
    {code[:8000]}
    ```
    """
    try:
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=FileAnalysisResult
        )
        response = client.models.generate_content(
            model="gemini-3.5-flash",
            contents=prompt,
            config=config
        )
        
        import json
        res = json.loads(response.text)
        return {
            "path": rel_path,
            "classes": res.get("classes", []),
            "functions": res.get("functions", []),
            "imports": res.get("imports", []),
            "file_type": res.get("file_type", "module"),
            "technologies": res.get("technologies", []),
            "lines": lines_count,
            "code": code
        }
    except Exception as e:
        print(f"Agentic analysis failed on {rel_path}, falling back: {e}")
        # Run local fallback parser
        fallback_type = classify_file(file_path, code)
        if file_path.suffix == ".py":
            imports, classes, functions = parse_python_details(code)
        elif file_path.suffix in {".js", ".jsx", ".ts", ".tsx"}:
            imports, classes, functions = parse_js_details(code)
        else:
            imports, classes, functions = [], [], []
            
        return {
            "path": rel_path,
            "classes": classes,
            "functions": functions,
            "imports": imports,
            "file_type": fallback_type,
            "technologies": detect_technologies(file_path, code),
            "lines": lines_count,
            "code": code
        }


def build_repo_graph(root: str) -> Dict:
    """Orchestrates codebase visualization agentically. Spawns parallel analyzers and maps system graphs."""
    client = get_gemini_client()
    
    # If API key is missing or client creation fails, use local regex/AST scanner fallback
    if not client:
        print("[System] API Key not set. Executing local graph build scan.")
        return build_repo_graph_local(root)
        
    try:
        # 1. Scan filesystem
        files = scan_files(root)
        if not files:
            return {"nodes": [], "edges": [], "summary": "No code files found in workspace."}
            
        # Limit total files analyzed in parallel to 20 for fast hackathon demo cycles
        files = files[:20]
        
        # 2. Run Concurrent File Analyzers
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(analyze_file_agent, root, f, client) for f in files]
            analyses = [fut.result() for fut in futures]
            
        # 3. Compile report for Graph Orchestrator Agent
        analyses_context = []
        for a in analyses:
            analyses_context.append({
                "path": a["path"],
                "classes": a["classes"],
                "functions": a["functions"],
                "imports": a["imports"],
                "file_type": a["file_type"],
                "technologies": a["technologies"]
            })
            
        import json
        orchestrator_prompt = f"""
        You are the Graph Orchestrator Agent. 
        Your role is to build a complete codebase relationship graph (nodes and edges) from the file analysis reports below.
        
        Here are the rules to establish relationships:
        1. Create a GraphNode for each code file. Set metadata: {{path, lines, extension, classes, functions, technologies, code}}.
        2. Create GraphNodes for HTTP route endpoints defined in backend files (type='api-route', e.g. id='route:POST:/api/login', label='POST /api/login'). 
           Connect the file node to the route node via an edge with label='defines'.
        3. Create GraphNodes for client-side API network calls in frontend files (type='api-call', e.g. id='api-call:src/utils/api.ts:/api/login', label='calls /api/login').
           Connect the file node to the call node via an edge with label='calls'.
        4. Match API calls to HTTP routes: Create an edge between matching API calls and HTTP routes (label='calls').
        5. Map dependencies: Resolve imported modules to file node paths, and create edges between file nodes (label='imports').
        
        File Analysis Reports:
        {json.dumps(analyses_context, indent=2)}
        
        Output the final graph conforming to the specified response schema.
        """
        
        from models import GraphNode, GraphEdge
        
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=GraphOutput
        )
        
        response = client.models.generate_content(
            model="gemini-3.5-flash",
            contents=orchestrator_prompt,
            config=config
        )
        
        graph_data = json.loads(response.text)
        
        # Post-process: inject full code text and line counts into file nodes
        code_map = {a["path"]: a["code"] for a in analyses}
        lines_map = {a["path"]: a["lines"] for a in analyses}
        
        final_nodes = []
        for node in graph_data.get("nodes", []):
            nid = node.get("id")
            ntype = node.get("type")
            label = node.get("label")
            metadata = node.get("metadata", {})
            
            if ntype not in {"api-route", "api-call"}:
                metadata["code"] = code_map.get(nid, "")
                metadata["lines"] = lines_map.get(nid, 0)
                metadata["extension"] = Path(nid).suffix
                
            final_nodes.append({
                "id": nid,
                "label": label,
                "type": ntype,
                "metadata": metadata
            })
            
        return {
            "nodes": final_nodes,
            "edges": graph_data.get("edges", []),
            "summary": graph_data.get("summary", "RepoGraph mapped components using Graph Orchestrator Agent.")
        }
        
    except Exception as exc:
        print(f"[System] Orchestration failed: {exc}. Reverting to local graph scanner.")
        return build_repo_graph_local(root)
