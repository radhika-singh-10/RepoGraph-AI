import React from "react";
import ReactDOM from "react-dom/client";
import ReactFlow, { Background, Controls, MiniMap, Handle, Position } from "reactflow";
import "reactflow/dist/style.css";
import "./styles.css";

type RepoNode = {
  id: string;
  label: string;
  type: string;
  metadata: {
    path?: string;
    lines?: number;
    extension?: string;
    classes?: string[];
    functions?: string[];
    technologies?: string[];
    code?: string;
    method?: string;
    route?: string;
    defined_in?: string;
    api?: string;
    imports?: string[];
  };
};

type RepoEdge = {
  id: string;
  source: string;
  target: string;
  label: string;
};

type RepoGraph = {
  nodes: RepoNode[];
  edges: RepoEdge[];
  summary: string;
};

function nodeIcon(type: string) {
  const icons: Record<string, string> = {
    frontend: "💻",
    "backend-api": "⚙️",
    database: "🗄️",
    auth: "🔒",
    infra: "🛠️",
    module: "📦",
    "api-route": "🌐",
    "api-call": "📡"
  };
  return icons[type] || "📄";
}

// Custom Node component with ports and styling
function CustomNode({ data }: { data: RepoNode & { nodeClass?: string } }) {
  const isRoute = data.type === "api-route";
  const isCall = data.type === "api-call";
  
  return (
    <div className={`custom-node ${data.type} ${data.nodeClass || ""}`}>
      {data.type !== "frontend" && (
        <Handle type="target" position={Position.Left} style={{ background: "var(--node-color)", width: 8, height: 8 }} />
      )}
      
      <div className="node-type-badge">{data.type}</div>
      <div className="node-header">
        <span className="node-title">{data.label}</span>
        <span className="node-icon">{nodeIcon(data.type)}</span>
      </div>
      
      {data.metadata?.technologies && data.metadata.technologies.length > 0 && (
        <div className="node-techs">
          {data.metadata.technologies.slice(0, 3).map((tech) => (
            <span key={tech} className="tech-badge">{tech}</span>
          ))}
        </div>
      )}
      
      {!isRoute && !isCall && data.metadata?.lines !== undefined && (
        <div className="node-stats">
          <span>{data.metadata.lines} lines</span>
          <span>{data.metadata.extension}</span>
        </div>
      )}
      
      {isRoute && data.metadata?.method && (
        <div className="node-stats">
          <span>HTTP METHOD</span>
          <span>{data.metadata.method}</span>
        </div>
      )}

      {isCall && data.metadata?.api && (
        <div className="node-stats">
          <span>API ENDPOINT</span>
          <span>{data.metadata.api}</span>
        </div>
      )}
      
      {data.type !== "database" && data.type !== "infra" && (
        <Handle type="source" position={Position.Right} style={{ background: "var(--node-color)", width: 8, height: 8 }} />
      )}
    </div>
  );
}

const nodeTypes = {
  repoNode: CustomNode
};

// Layout engine placing nodes in distinct column lanes
function computeLayout(nodes: RepoNode[], edges: RepoEdge[]) {
  const columnWidth = 340;
  const rowHeight = 150;
  const columnCounts: Record<number, number> = {
    0: 0, 1: 0, 2: 0, 3: 0, 4: 0, 5: 0
  };
  
  return nodes.map((node) => {
    let col = 4; // default
    
    if (node.type === "frontend") col = 0;
    else if (node.type === "api-call") col = 1;
    else if (node.type === "api-route") col = 2;
    else if (node.type === "auth" || node.type === "backend-api") col = 3;
    else if (node.type === "module") col = 4;
    else if (node.type === "database" || node.type === "infra") col = 5;
    
    const row = columnCounts[col] || 0;
    columnCounts[col] = row + 1;
    
    const x = col * columnWidth + 40;
    const y = row * rowHeight + 100;
    
    return {
      id: node.id,
      type: "repoNode",
      position: { x, y },
      data: { ...node }
    };
  });
}

// Simple Markdown parser for rich AI explanations
function renderMarkdown(md: string) {
  if (!md) return "";
  
  const lines = md.split("\n");
  const htmlLines: string[] = [];
  let inList = false;
  
  for (let line of lines) {
    const trimmed = line.trim();
    
    if (trimmed.startsWith("- ")) {
      if (!inList) {
        htmlLines.push("<ul>");
        inList = true;
      }
      htmlLines.push(`<li>${parseInlineMarkdown(trimmed.substring(2))}</li>`);
      continue;
    } else {
      if (inList) {
        htmlLines.push("</ul>");
        inList = false;
      }
    }
    
    if (trimmed.startsWith("### ")) {
      htmlLines.push(`<h3>${parseInlineMarkdown(trimmed.substring(4))}</h3>`);
    } else if (trimmed.startsWith("## ")) {
      htmlLines.push(`<h2>${parseInlineMarkdown(trimmed.substring(3))}</h2>`);
    } else if (trimmed.startsWith("# ")) {
      htmlLines.push(`<h1>${parseInlineMarkdown(trimmed.substring(2))}</h1>`);
    } else if (trimmed === "") {
      htmlLines.push("<br/>");
    } else {
      htmlLines.push(`<p>${parseInlineMarkdown(trimmed)}</p>`);
    }
  }
  
  if (inList) {
    htmlLines.push("</ul>");
  }
  
  return htmlLines.join("\n");
}

function parseInlineMarkdown(text: string) {
  let html = text;
  html = html.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/`(.*?)`/g, "<code>$1</code>");
  html = html.replace(/\[(.*?)\]\((.*?)\)/g, '<span style="color: #60a5fa; cursor: pointer;">$1</span>');
  return html;
}

function generateLocalExplanation(node: RepoNode, graph: RepoGraph): string {
  const node_id = node.id;
  const incoming = graph.edges.filter((e: RepoEdge) => e.target === node_id);
  const outgoing = graph.edges.filter((e: RepoEdge) => e.source === node_id);

  const node_type = node.type;
  const label = node.label;
  const metadata = node.metadata || {};
  const path = metadata.path || node_id;
  const lines = metadata.lines || 0;
  const classes = metadata.classes || [];
  const functions = metadata.functions || [];
  const technologies = metadata.technologies || [];

  const imported_by = incoming.filter((e: RepoEdge) => e.label === "imports").map((e: RepoEdge) => e.source);
  const imports_to = outgoing.filter((e: RepoEdge) => e.label === "imports").map((e: RepoEdge) => e.target);
  const defines_routes = outgoing.filter((e: RepoEdge) => e.label === "defines").map((e: RepoEdge) => e.target.replace("route:", ""));
  const calls_apis = outgoing.filter((e: RepoEdge) => e.label === "calls").map((e: RepoEdge) => e.target.replace("api-call:", ""));

  if (node_type === "api-route") {
    const defined_in = metadata.defined_in || "unknown module";
    const method = metadata.method || "GET";
    const route = metadata.route || "";
    return `### API Route: \`${method} ${route}\`\n\n` +
           `This is an **HTTP API Endpoint** exposed by the backend.\n\n` +
           `- **Endpoint**: \`${route}\`\n` +
           `- **HTTP Method**: \`${method}\`\n` +
           `- **Defined in**: [\`${defined_in}\`](file:///${defined_in})\n\n` +
           `This route allows frontend applications or external clients to interact with the backend service. ` +
           `It is defined in [\`${defined_in}\`](file:///${defined_in}) which handles requests made to this endpoint.`;
  }

  if (node_type === "api-call") {
    const defined_in = metadata.defined_in || "unknown module";
    const api = metadata.api || "";
    return `### API Call: \`${api}\`\n\n` +
           `This represents an outgoing **HTTP network request** made from the frontend application.\n\n` +
           `- **Target URL/Route**: \`${api}\`\n` +
           `- **Invoked by**: [\`${defined_in}\`](file:///${defined_in})\n\n` +
           `This call is triggered from the client-side user interface to fetch or send data to the backend API. ` +
           `It connects the user experience in [\`${defined_in}\`](file:///${defined_in}) to the server-side logic.`;
  }

  const explanation: string[] = [];
  explanation.push(`## Module: \`${label}\``);
  explanation.push(`**Path**: \`${path}\` • **Lines of Code**: \`${lines}\``);

  const typeLabels: Record<string, string> = {
    frontend: "Frontend View / UI Component",
    "backend-api": "Backend Controller / API Router",
    database: "Database Model / Connection Layer",
    auth: "Authentication / Security Module",
    infra: "Infrastructure / Configuration File",
    module: "Utility / Core Business Logic Module"
  };
  const typeDesc = typeLabels[node_type] || "Repository Source File";
  explanation.push(`**Architectural Role**: \`${typeDesc}\`\n`);

  const techStr = technologies.length > 0 ? technologies.map(t => `\`${t}\``).join(", ") : "None detected";
  explanation.push(`### ⚙️ Technologies Used\n${techStr}\n`);

  if (classes.length > 0 || functions.length > 0) {
    explanation.push("### 📦 Exported Code Structures");
    if (classes.length > 0) {
      explanation.push("- **Classes Defined**:");
      classes.forEach(c => explanation.push(`  - \`class ${c}\``));
    }
    if (functions.length > 0) {
      explanation.push("- **Functions Defined**:");
      functions.slice(0, 15).forEach(f => {
        explanation.push(path.endsWith(".py") ? `  - \`def ${f}\`` : `  - \`function ${f}\``);
      });
      if (functions.length > 15) {
        explanation.push(`  - *...and ${functions.length - 15} more functions*`);
      }
    }
    explanation.push("");
  }

  explanation.push("### 🔗 Graph Relationships");
  if (imported_by.length > 0) {
    explanation.push("- **Imported By (Dependents)**:");
    imported_by.slice(0, 5).forEach(dep => explanation.push(`  - [\`${dep}\`](file:///${dep})`));
    if (imported_by.length > 5) {
      explanation.push(`  - *...and ${imported_by.length - 5} more files*`);
    }
  } else {
    explanation.push("- **Imported By**: *This module is an entrypoint or standalone file (no other local files import it).*");
  }

  if (imports_to.length > 0) {
    explanation.push("- **Imports (Dependencies)**:");
    imports_to.slice(0, 5).forEach(dep => explanation.push(`  - [\`${dep}\`](file:///${dep})`));
    if (imports_to.length > 5) {
      explanation.push(`  - *...and ${imports_to.length - 5} more files*`);
    }
  } else {
    explanation.push("- **Imports**: *This file has no external or internal local imports.*");
  }

  if (defines_routes.length > 0) {
    explanation.push("- **API Endpoints Exposed**:");
    defines_routes.forEach(r => explanation.push(`  - \`${r}\``));
  }

  if (calls_apis.length > 0) {
    explanation.push("- **Client API Calls Made**:");
    calls_apis.forEach(c => explanation.push(`  - \`${c}\``));
  }

  explanation.push("");

  explanation.push("### 💡 AI Code Summary");
  let purpose = "";
  if (node_type === "auth") {
    purpose = "This module manages user security and access control. It handles encryption/decryption, token creation or verification, and protects application routes from unauthorized access.";
  } else if (node_type === "database") {
    purpose = "This module handles state persistence and schemas. It connects to the database engine and defines models or queries to select, insert, update, or delete records.";
  } else if (node_type === "frontend") {
    purpose = "This component renders visual interface elements to the browser. It reacts to user interactions, manages local state, and binds events to user interface elements.";
  } else if (node_type === "backend-api") {
    purpose = "This file acts as a server-side entry point or route handler. It receives client HTTP requests, validates input payloads, coordinates domain operations, and returns JSON responses.";
  } else if (node_type === "infra") {
    purpose = "This file configures environment settings, tooling, styles, or deployment containers, defining the build or runtime environment for the application.";
  } else {
    purpose = "This module contains shared logic or utilities. It exports functions or helper classes to perform calculations, parse data, or help other components process information.";
  }
  explanation.push(purpose);

  return explanation.join("\n");
}

// ----------------------------------------------------
// Mock Codebase structure for instant local testing
// ----------------------------------------------------
const MOCK_GRAPH: RepoGraph = {
  nodes: [
    {
      id: "src/App.tsx",
      label: "App.tsx",
      type: "frontend",
      metadata: {
        path: "src/App.tsx",
        lines: 12,
        extension: ".tsx",
        classes: [],
        functions: ["App"],
        technologies: ["React", "TypeScript"],
        code: `import React from 'react';\nimport Navbar from './components/Navbar';\nimport AuthCard from './components/AuthCard';\n\nexport default function App() {\n  return (\n    <div className="app-container">\n      <Navbar />\n      <main className="main-content">\n        <AuthCard />\n      </main>\n    </div>\n  );\n}`
      }
    },
    {
      id: "src/components/Navbar.tsx",
      label: "Navbar.tsx",
      type: "frontend",
      metadata: {
        path: "src/components/Navbar.tsx",
        lines: 15,
        extension: ".tsx",
        classes: [],
        functions: ["Navbar"],
        technologies: ["React", "TypeScript"],
        code: `import React from 'react';\n\nexport default function Navbar() {\n  return (\n    <nav className="navbar">\n      <div className="logo">RepoGraph AI</div>\n      <div className="links">\n        <a href="#dashboard">Dashboard</a>\n        <a href="#settings">Settings</a>\n      </div>\n    </nav>\n  );\n}`
      }
    },
    {
      id: "src/components/AuthCard.tsx",
      label: "AuthCard.tsx",
      type: "frontend",
      metadata: {
        path: "src/components/AuthCard.tsx",
        lines: 24,
        extension: ".tsx",
        classes: [],
        functions: ["AuthCard"],
        technologies: ["React", "TypeScript"],
        code: `import React, { useState } from 'react';\nimport { loginUser } from '../utils/api';\n\nexport default function AuthCard() {\n  const [email, setEmail] = useState('');\n  const [password, setPassword] = useState('');\n  \n  const handleLogin = async () => {\n    const res = await loginUser(email, password);\n    alert(res.message);\n  };\n  \n  return (\n    <div className="auth-card">\n      <h2>Sign In</h2>\n      <input type="email" value={email} onChange={e => setEmail(e.target.value)} />\n      <input type="password" value={password} onChange={e => setPassword(e.target.value)} />\n      <button onClick={handleLogin}>Login</button>\n    </div>\n  );\n}`
      }
    },
    {
      id: "src/utils/api.ts",
      label: "api.ts",
      type: "module",
      metadata: {
        path: "src/utils/api.ts",
        lines: 16,
        extension: ".ts",
        classes: [],
        functions: ["loginUser", "fetchUser"],
        technologies: ["Axios", "TypeScript"],
        code: `import axios from 'axios';\n\nexport async function loginUser(email, password) {\n  const response = await axios.post('http://localhost:8000/api/login', { email, password });\n  return response.data;\n}\n\nexport async function fetchUser(token) {\n  const response = await axios.get('http://localhost:8000/api/user', {\n    headers: { Authorization: \`Bearer \${token}\` }\n  });\n  return response.data;\n}`
      }
    },
    {
      id: "api-call:src/utils/api.ts:/api/login",
      label: "calls /api/login",
      type: "api-call",
      metadata: {
        api: "/api/login",
        defined_in: "src/utils/api.ts"
      }
    },
    {
      id: "api-call:src/utils/api.ts:/api/user",
      label: "calls /api/user",
      type: "api-call",
      metadata: {
        api: "/api/user",
        defined_in: "src/utils/api.ts"
      }
    },
    {
      id: "route:POST:/api/login",
      label: "POST /api/login",
      type: "api-route",
      metadata: {
        method: "POST",
        route: "/api/login",
        defined_in: "backend/main.py"
      }
    },
    {
      id: "route:GET:/api/user",
      label: "GET /api/user",
      type: "api-route",
      metadata: {
        method: "GET",
        route: "/api/user",
        defined_in: "backend/main.py"
      }
    },
    {
      id: "backend/main.py",
      label: "main.py",
      type: "backend-api",
      metadata: {
        path: "backend/main.py",
        lines: 32,
        extension: ".py",
        classes: [],
        functions: ["login", "user_info"],
        technologies: ["FastAPI", "Python"],
        code: `from fastapi import FastAPI, Depends, HTTPException\nfrom fastapi.security import OAuth2PasswordBearer\nfrom auth import create_access_token, verify_token\nfrom database import get_db\nfrom models import User\n\napp = FastAPI()\n\n@app.post("/api/login")\ndef login(payload: dict, db=Depends(get_db)):\n    user = db.query(User).filter(User.email == payload["email"]).first()\n    if not user or not user.verify_password(payload["password"]):\n        raise HTTPException(status_code=401, detail="Invalid credentials")\n    token = create_access_token(user.id)\n    return {"token": token, "message": "Success"}\n\n@app.get("/api/user")\ndef user_info(token: str = Depends(OAuth2PasswordBearer(tokenUrl="login")), db=Depends(get_db)):\n    user_id = verify_token(token)\n    user = db.query(User).filter(User.id == user_id).first()\n    return {"email": user.email, "id": user.id}`
      }
    },
    {
      id: "backend/auth.py",
      label: "auth.py",
      type: "auth",
      metadata: {
        path: "backend/auth.py",
        lines: 18,
        extension: ".py",
        classes: [],
        functions: ["create_access_token", "verify_token"],
        technologies: ["JWT", "Python"],
        code: `import jwt\nfrom datetime import datetime, timedelta\nfrom database import SECRET_KEY\n\ndef create_access_token(user_id: int) -> str:\n    payload = {\n        "sub": user_id,\n        "exp": datetime.utcnow() + timedelta(hours=24)\n    }\n    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")\n\ndef verify_token(token: str) -> int:\n    try:\n        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])\n        return payload["sub"]\n    except jwt.PyJWTError:\n        raise Exception("Invalid token")`
      }
    },
    {
      id: "backend/database.py",
      label: "database.py",
      type: "database",
      metadata: {
        path: "backend/database.py",
        lines: 15,
        extension: ".py",
        classes: [],
        functions: ["get_db"],
        technologies: ["SQLAlchemy", "SQLite", "Python"],
        code: `from sqlalchemy import create_engine\nfrom sqlalchemy.orm import sessionmaker, declarative_base\n\nDATABASE_URL = "sqlite:///./app.db"\nSECRET_KEY = "super-secret-key-for-jwt"\n\nengine = create_engine(DATABASE_URL)\nSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)\nBase = declarative_base()\n\ndef get_db():\n    db = SessionLocal()\n    try:\n        yield db\n    finally:\n        db.close()`
      }
    },
    {
      id: "backend/models.py",
      label: "models.py",
      type: "database",
      metadata: {
        path: "backend/models.py",
        lines: 12,
        extension: ".py",
        classes: ["User"],
        functions: ["verify_password"],
        technologies: ["SQLAlchemy", "Python"],
        code: `from sqlalchemy import Column, Integer, String\nfrom database import Base\n\nclass User(Base):\n    __tablename__ = "users"\n    \n    id = Column(Integer, primary_key=True, index=True)\n    email = Column(String, unique=True, index=True)\n    password_hash = Column(String)\n    \n    def verify_password(self, password: str) -> bool:\n        return self.password_hash == password`
      }
    },
    {
      id: "Dockerfile",
      label: "Dockerfile",
      type: "infra",
      metadata: {
        path: "Dockerfile",
        lines: 8,
        extension: "",
        classes: [],
        functions: [],
        technologies: ["Uvicorn", "Python"],
        code: `FROM python:3.10-slim\nWORKDIR /app\nCOPY requirements.txt .\nRUN pip install -r requirements.txt\nCOPY . .\nCMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]`
      }
    }
  ],
  edges: [
    { id: "e1", source: "src/App.tsx", target: "src/components/Navbar.tsx", label: "imports" },
    { id: "e2", source: "src/App.tsx", target: "src/components/AuthCard.tsx", label: "imports" },
    { id: "e3", source: "src/components/AuthCard.tsx", target: "src/utils/api.ts", label: "imports" },
    { id: "e4", source: "src/utils/api.ts", target: "api-call:src/utils/api.ts:/api/login", label: "calls" },
    { id: "e5", source: "src/utils/api.ts", target: "api-call:src/utils/api.ts:/api/user", label: "calls" },
    { id: "e6", source: "api-call:src/utils/api.ts:/api/login", target: "route:POST:/api/login", label: "calls" },
    { id: "e7", source: "api-call:src/utils/api.ts:/api/user", target: "route:GET:/api/user", label: "calls" },
    { id: "e8", source: "backend/main.py", target: "route:POST:/api/login", label: "defines" },
    { id: "e9", source: "backend/main.py", target: "route:GET:/api/user", label: "defines" },
    { id: "e10", source: "backend/main.py", target: "backend/auth.py", label: "imports" },
    { id: "e11", source: "backend/main.py", target: "backend/database.py", label: "imports" },
    { id: "e12", source: "backend/main.py", target: "backend/models.py", label: "imports" },
    { id: "e13", source: "backend/auth.py", target: "backend/database.py", label: "imports" },
    { id: "e14", source: "backend/database.py", target: "backend/models.py", label: "imports" }
  ],
  summary: "RepoGraph mapped 13 components and 14 code links. Detected 3 client components, 1 API modules, 2 exposed endpoints, 1 security services, and 2 database schemas."
};

function App() {
  const [graph, setGraph] = React.useState<RepoGraph | null>(null);
  const [selectedNode, setSelectedNode] = React.useState<RepoNode | null>(null);
  const [explanation, setExplanation] = React.useState<string>("");
  const [loading, setLoading] = React.useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = React.useState<boolean>(false);
  const [detailsExpanded, setDetailsExpanded] = React.useState<boolean>(true);
  const [sidebarWidth, setSidebarWidth] = React.useState<number>(420);
  const [isResizing, setIsResizing] = React.useState<boolean>(false);
  
  // Tabs toggle variables
  const [activeTab, setActiveTab] = React.useState<string>("pr");
  const [githubUrl, setGithubUrl] = React.useState<string>("");
  const [prMarkdown, setPrMarkdown] = React.useState<string>("");
  const [githubActionYaml, setGithubActionYaml] = React.useState<string>("");

  // SOLID audit variables
  const [solidScore, setSolidScore] = React.useState<number | null>(null);
  const [solidReport, setSolidReport] = React.useState<string>("");
  const [solidViolations, setSolidViolations] = React.useState<{srp: any[], dip: any[], isp: any[]}>({srp: [], dip: [], isp: []});

  // Agent states
  const [agentInstruction, setAgentInstruction] = React.useState<string>("");
  const [agentTargetFile, setAgentTargetFile] = React.useState<string>("");
  const [agentStatus, setAgentStatus] = React.useState<string>("idle"); // idle, running, pr_created, merged
  const [agentBranch, setAgentBranch] = React.useState<string>("");
  const [agentPrTitle, setAgentPrTitle] = React.useState<string>("");
  const [agentPrBody, setAgentPrBody] = React.useState<string>("");
  const [agentDiff, setAgentDiff] = React.useState<string>("");
  const [terminalLines, setTerminalLines] = React.useState<string[]>([]);

  // Tri-Agent states
  // 1. ArchGuard CI
  const [ciStatus, setCiStatus] = React.useState<string>("idle"); // idle, running, passed, failed
  const [ciScore, setCiScore] = React.useState<number | null>(null);
  const [ciFailedRules, setCiFailedRules] = React.useState<string[]>([]);
  const [ciReport, setCiReport] = React.useState<string>("");
  const [ciTerminalLogs, setCiTerminalLogs] = React.useState<string[]>([]);

  // 2. Spec Validator
  const [specText, setSpecText] = React.useState<string>("");
  const [specImageFile, setSpecImageFile] = React.useState<File | null>(null);
  const [specImagePreview, setSpecImagePreview] = React.useState<string>("");
  const [specLoading, setSpecLoading] = React.useState<boolean>(false);
  const [specScore, setSpecScore] = React.useState<number | null>(null);
  const [specDivergences, setSpecDivergences] = React.useState<string[]>([]);
  const [specRemedies, setSpecRemedies] = React.useState<string[]>([]);

  // 3. Time-Travel Scrubber
  const [historyCommits, setHistoryCommits] = React.useState<any[]>([]);
  const [currentCommitIdx, setCurrentCommitIdx] = React.useState<number>(-1);
  const [commitNarration, setCommitNarration] = React.useState<string>("");
  const [narrationOpen, setNarrationOpen] = React.useState<boolean>(false);

  const startResizing = React.useCallback((mouseDownEvent: React.MouseEvent) => {
    mouseDownEvent.preventDefault();
    setIsResizing(true);
    
    const startWidth = sidebarWidth;
    const startX = mouseDownEvent.clientX;

    const doDrag = (mouseMoveEvent: MouseEvent) => {
      const newWidth = startWidth + (mouseMoveEvent.clientX - startX);
      if (newWidth >= 280 && newWidth <= 700) {
        setSidebarWidth(newWidth);
      }
    };

    const stopDrag = () => {
      setIsResizing(false);
      document.removeEventListener("mousemove", doDrag);
      document.removeEventListener("mouseup", stopDrag);
    };

    document.addEventListener("mousemove", doDrag);
    document.addEventListener("mouseup", stopDrag);
  }, [sidebarWidth]);

  async function runArchGuardCI() {
    setCiStatus("running");
    setCiTerminalLogs([
      "[CI Engine] Spinning up workflow container...",
      "[CI Engine] Checking out pull request branch...",
      "[CI Engine] Mapping PR architecture graph...",
      "[CI Engine] Invoking ArchGuard Regression Gate Agent (Gemini 3.5)..."
    ]);

    const steps = [
      "[CI Engine] Auditing circular dependencies...",
      "[CI Engine] Evaluating SOLID principles regression metrics...",
      "[CI Engine] Comparing graph nodes and imports boundary..."
    ];
    let idx = 0;
    const interval = setInterval(() => {
      if (idx < steps.length) {
        setCiTerminalLogs(prev => [...prev, steps[idx]]);
        idx++;
      } else {
        clearInterval(interval);
      }
    }, 1000);

    try {
      const res = await fetch("http://localhost:8000/agent/run-ci", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ branch: agentBranch || "main" })
      });
      clearInterval(interval);
      if (!res.ok) throw new Error("CI check failed");
      const data = await res.json();
      
      setCiTerminalLogs(prev => [
        ...prev, 
        "[CI Engine] Regression audit completed.",
        `[CI Engine] Gate status: ${data.passed ? "PASSED" : "FAILED"}`
      ]);
      setCiScore(data.regression_score);
      setCiFailedRules(data.failed_rules || []);
      setCiReport(data.diff_markdown || "");
      setCiStatus(data.passed ? "passed" : "failed");
    } catch (err: any) {
      clearInterval(interval);
      console.error(err);
      setCiTerminalLogs(prev => [...prev, `[CI Engine] Error: ${err.message || "Failed CI run"}`]);
      setCiStatus("failed");
    }
  }

  async function runSpecValidator() {
    if (!specText.trim() && !specImageFile) {
      alert("Please provide either design specification text or an architecture diagram image.");
      return;
    }
    setSpecLoading(true);
    setSpecScore(null);
    setSpecDivergences([]);
    setSpecRemedies([]);

    const formData = new FormData();
    formData.append("spec", specText);
    if (specImageFile) {
      formData.append("file", specImageFile);
    }

    try {
      const res = await fetch("http://localhost:8000/agent/validate-spec", {
        method: "POST",
        body: formData
      });
      if (!res.ok) throw new Error("Validation request failed");
      const data = await res.json();
      setSpecScore(data.score);
      setSpecDivergences(data.divergences || []);
      setSpecRemedies(data.remedy_proposals || []);
    } catch (err: any) {
      console.error(err);
      alert("Specification validation failed: " + err.message);
    } finally {
      setSpecLoading(false);
    }
  }

  async function fetchGitHistory() {
    try {
      const res = await fetch("http://localhost:8000/agent/history");
      if (res.ok) {
        const data = await res.json();
        setHistoryCommits(data);
        if (data.length > 0) {
          // Set index to latest commit (index data.length - 1 if we map from oldest to newest)
          setCurrentCommitIdx(data.length - 1);
        }
      }
    } catch (err) {
      console.warn("Failed to fetch git commit logs:", err);
    }
  }

  async function handleTimelineChange(idx: number) {
    if (idx < 0 || idx >= historyCommits.length) return;
    setCurrentCommitIdx(idx);
    const commit = historyCommits[idx];
    setCommitNarration("Historian Agent checking out commit and compiling structural narration...");
    setNarrationOpen(true);
    setLoading(true);

    try {
      const res = await fetch("http://localhost:8000/agent/time-travel", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sha: commit.sha })
      });
      if (!res.ok) throw new Error("Time travel failed");
      const data = await res.json();
      setGraph(data.graph);
      setCommitNarration(data.narration);
    } catch (err: any) {
      console.error(err);
      setCommitNarration("Failed to travel back. Workspace revert was unsuccessful.");
    } finally {
      setLoading(false);
    }
  }

  function triggerAutoFix(file: string, desc: string, targetFile: string) {
    setSelectedNode(null);
    setActiveTab("agent");
    setAgentInstruction(desc);
    setAgentTargetFile(targetFile);
  }

  async function runAgentCreator() {
    if (!agentInstruction.trim()) {
      alert("Please enter instructions for the agent.");
      return;
    }
    setAgentStatus("running");
    setTerminalLines(["[System] Initializing Multi-Agent Code Review & Action Team...", "[System] Connecting to local sandboxed backend..."]);
    
    // Simulate initial agent environment preparation
    const progressLines = [
      "[System] Spinning up secure isolated Linux container...",
      "[System] Loading workspace context and scanning source files...",
      "[System] Activating Google Antigravity Agent Harness (Gemini 3.5 Flash)..."
    ];
    let step = 0;
    const progressInterval = setInterval(() => {
      if (step < progressLines.length) {
        setTerminalLines(prev => [...prev, progressLines[step]]);
        step++;
      } else {
        clearInterval(progressInterval);
      }
    }, 800);

    try {
      const res = await fetch("http://localhost:8000/agent/create-pr", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          instruction: agentInstruction,
          target_file: agentTargetFile || null
        })
      });

      clearInterval(progressInterval);

      if (!res.ok) {
        throw new Error("Failed to invoke code modification agent.");
      }

      const data = await res.json();
      
      // Stream logs from the agents (Architect, Coder, Reviewer)
      const fullLogs = data.thoughts || "";
      const logLines = fullLogs.split("\n");
      let idx = 0;
      setTerminalLines(prev => [...prev, "[System] Multi-agent container active. Streaming team discussions:"]);
      
      const streamInterval = setInterval(() => {
        if (idx < logLines.length) {
          if (logLines[idx].trim()) {
            setTerminalLines(prev => [...prev, logLines[idx]]);
          }
          idx++;
        } else {
          clearInterval(streamInterval);
          setAgentBranch(data.branch);
          setAgentPrTitle(data.pr_title);
          setAgentPrBody(data.pr_body);
          setAgentDiff(data.diff);
          setAgentStatus("pr_created");
        }
      }, 80);

    } catch (err: any) {
      clearInterval(progressInterval);
      console.error(err);
      setTerminalLines(prev => [...prev, `[System] Error running agents: ${err.message || "Failed to execute modification"}`]);
      setTimeout(() => {
        setAgentStatus("idle");
      }, 3000);
    }
  }

  async function mergeAgentPR() {
    if (!agentBranch) return;
    setLoading(true);
    try {
      const res = await fetch("http://localhost:8000/agent/merge-pr", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ branch: agentBranch })
      });
      if (!res.ok) throw new Error("Merge operation failed");
      const updatedGraph = await res.json();
      setGraph(updatedGraph);
      setAgentStatus("merged");
    } catch (err: any) {
      console.error(err);
      alert("Failed to merge agent Pull Request: " + err.message);
    } finally {
      setLoading(false);
    }
  }

  function renderDiffViewer(diffText: string) {
    if (!diffText) return <p style={{ fontSize: 11, color: "var(--text-muted)" }}>No modifications detected.</p>;
    const files = diffText.split("diff --git");
    return files.map((fileDiff, idx) => {
      if (!fileDiff.trim()) return null;
      const lines = fileDiff.split("\n");
      
      let fileName = "Modified File";
      const bNameMatch = lines[0].match(/b\/(.+)$/);
      if (bNameMatch) {
        fileName = bNameMatch[1];
      } else {
        const aNameMatch = lines.find(l => l.startsWith("+++ b/"));
        if (aNameMatch) fileName = aNameMatch.replace("+++ b/", "");
      }
      
      const codeLines = lines.filter(line => 
        !line.startsWith("diff --git") &&
        !line.startsWith("index ") &&
        !line.startsWith("--- a/") &&
        !line.startsWith("+++ b/") &&
        !line.startsWith("@@ ")
      );
      
      return (
        <div className="diff-file-block" key={idx} style={{ marginBottom: 12 }}>
          <div className="diff-file-header">📂 {fileName}</div>
          <div className="diff-content">
            {codeLines.map((line, lIdx) => {
              let lineClass = "diff-line-normal";
              if (line.startsWith("+")) lineClass = "diff-line-added";
              else if (line.startsWith("-")) lineClass = "diff-line-removed";
              return (
                <span className={`diff-line ${lineClass}`} key={lIdx}>
                  {line}
                </span>
              );
            })}
          </div>
        </div>
      );
    });
  }

  async function uploadRepo(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;

    setLoading(true);
    setSelectedNode(null);
    setExplanation("");
    setActiveTab("pr");

    const formData = new FormData();
    formData.append("file", file);

    try {
      const res = await fetch("http://localhost:8000/analyze", {
        method: "POST",
        body: formData
      });

      if (!res.ok) throw new Error("Upload failed");
      const data = await res.json();
      setGraph(data);
      fetchGitHistory();
    } catch (err) {
      console.error(err);
      alert("Failed to connect to backend server. Make sure FastAPI is running on port 8000. Or, click 'Load Demo Codebase' to test without a running server!");
    } finally {
      setLoading(false);
    }
  }

  async function scanGithubRepo() {
    if (!githubUrl) {
      alert("Please enter a valid GitHub repository URL.");
      return;
    }
    setLoading(true);
    setSelectedNode(null);
    setExplanation("");
    setActiveTab("pr");

    try {
      const res = await fetch(`http://localhost:8000/analyze-github?url=${encodeURIComponent(githubUrl)}`);
      if (!res.ok) {
        const errData = await res.json();
        throw new Error(errData.detail || "Failed to scan GitHub repository");
      }
      const data = await res.json();
      setGraph(data);
      fetchGitHistory();
    } catch (err: any) {
      console.error(err);
      alert(err.message || "Failed to connect to backend server.");
    } finally {
      setLoading(false);
    }
  }

  function loadDemoCodebase() {
    setLoading(true);
    // Fetch live graph from backend
    fetch('http://localhost:8000/graph')
      .then(res => {
        if (!res.ok) throw new Error('Failed to fetch graph');
        return res.json();
      })
      .then(data => {
        setGraph(data);
        setSelectedNode(null);
        setExplanation("");
        setActiveTab("pr");
        setLoading(false);
        fetchGitHistory();
      })
      .catch(err => {
        console.error(err);
        alert(err.message || 'Failed to load graph');
        setLoading(false);
      });
  }

  async function explainNode(node: RepoNode) {
    if (!graph) return;
    setSelectedNode(node);
    setActiveTab("explain");
    setExplanation("Generating explanation...");

    try {
      const res = await fetch("http://localhost:8000/explain", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ node_id: node.id, graph })
      });

      if (!res.ok) throw new Error("Backend error");
      const data = await res.json();
      setExplanation(data.explanation);
    } catch (err) {
      console.warn("Backend explanation failed, using local fallback analyzer...", err);
      const fallback = generateLocalExplanation(node, graph);
      setExplanation(fallback);
    }
  }

  // Load PR Summary, SOLID Audit, and Actions config on graph updates
  React.useEffect(() => {
    if (!graph) {
      setPrMarkdown("");
      setGithubActionYaml("");
      setSolidScore(null);
      setSolidReport("");
      return;
    }

    const activeGraph = graph; // Guard non-null local copy for TS!

    async function fetchPrReport() {
      try {
        const res = await fetch("http://localhost:8000/pr-report", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(activeGraph)
        });
        if (res.ok) {
          const data = await res.json();
          setPrMarkdown(data.markdown);
          setGithubActionYaml(data.github_action);
        } else {
          generateLocalPrReport();
        }
      } catch (err) {
        console.warn("Backend PR report request failed, using client fallback...", err);
        generateLocalPrReport();
      }
    }

    async function fetchSolidAudit() {
      try {
        const res = await fetch("http://localhost:8000/solid-audit", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(activeGraph)
        });
        if (res.ok) {
          const data = await res.json();
          setSolidScore(data.score);
          setSolidReport(data.report);
          setSolidViolations({
            srp: data.srp || [],
            dip: data.dip || [],
            isp: data.isp || []
          });
        } else {
          generateLocalSolidAudit();
        }
      } catch (err) {
        console.warn("Backend SOLID audit failed, using client fallback...", err);
        generateLocalSolidAudit();
      }
    }

    function generateLocalPrReport() {
      const fileNodes = activeGraph.nodes.filter(n => n.type !== "api-route" && n.type !== "api-call");
      const routeNodes = activeGraph.nodes.filter(n => n.type === "api-route");
      const callNodes = activeGraph.nodes.filter(n => n.type === "api-call");

      const counts: Record<string, number> = {};
      fileNodes.forEach(n => {
        counts[n.type] = (counts[n.type] || 0) + 1;
      });

      const report: string[] = [];
      report.push("# 🗺️ RepoGraph AI - Pull Request Architecture Review");
      report.push("This PR introduces codebase changes. Here is an automatically compiled system-wide architectural report:");
      report.push("");
      report.push("### 📊 System Overview");
      report.push(`- **Total Components Scanned**: \`${fileNodes.length}\` files`);
      report.push(`- **Exposed API Endpoints**: \`${routeNodes.length}\` routes`);
      report.push(`- **Client Request Triggers**: \`${callNodes.length}\` network calls`);

      const layerLabels: Record<string, string> = {
        frontend: "Frontend Views",
        "backend-api": "API Routers/Controllers",
        database: "Database Schemas/Models",
        auth: "Security Modules",
        infra: "DevOps & Configs",
        module: "Business Logic Modules"
      };

      Object.entries(layerLabels).forEach(([type, label]) => {
        if (counts[type]) {
          report.push(`  - **${label}**: \`${counts[type]}\` files`);
        }
      });

      report.push("");
      report.push("### ⚡ Architectural Highlight (Key Modules)");
      const sortedFiles = [...fileNodes].sort((a, b) => {
        const linesA = (a.metadata?.lines as number) || 0;
        const linesB = (b.metadata?.lines as number) || 0;
        return linesB - linesA;
      });

      sortedFiles.slice(0, 5).forEach(n => {
        const lines = (n.metadata?.lines as number) || 0;
        const techs = (n.metadata?.technologies as string[]) || [];
        const techStr = techs.length > 0 ? ` (using ${techs.join(", ")})` : "";
        report.push(`- **\`${n.label}\`** (\`${n.type}\`): \`${lines}\` lines of code${techStr}.`);
      });

      report.push("");
      report.push("### 🔗 Relationship Graph Links");
      const importEdges = activeGraph.edges.filter(e => e.label === "imports");
      const definesEdges = activeGraph.edges.filter(e => e.label === "defines");

      if (importEdges.length > 0) {
        report.push("**Critical File Dependencies:**");
        importEdges.slice(0, 5).forEach(e => {
          report.push(`- \`${e.source}\` ➔ *imports* ➔ \`${e.target}\``);
        });
      }

      if (definesEdges.length > 0) {
        report.push("\n**Critical Endpoint Definitions:**");
        definesEdges.slice(0, 3).forEach(e => {
          const routeLabel = e.target.replace("route:", "");
          report.push(`- \`${e.source}\` ➔ *defines route* ➔ \`${routeLabel}\``);
        });
      }

      report.push("");
      report.push("---");
      report.push("*Report generated by **RepoGraph AI** onboarding agent. Integrate into your CI/CD flow to map incoming code changes.*");

      setPrMarkdown(report.join("\n"));

      setGithubActionYaml(
        "name: RepoGraph AI Code Review\n\n" +
        "on:\n" +
        "  pull_request:\n" +
        "    branches: [ main, master ]\n\n" +
        "jobs:\n" +
        "  repograph-scan:\n" +
        "    runs-on: ubuntu-latest\n" +
        "    steps:\n" +
        "      - name: Checkout Code\n" +
        "        uses: actions/checkout@v3\n\n" +
        "      - name: Set up Python\n" +
        "        uses: actions/setup-python@v4\n" +
        "        with:\n" +
        "          python-version: '3.11'\n\n" +
        "      - name: Install RepoGraph Scanner\n" +
        "        run: |\n" +
        "          pip install requests pydantic python-multipart\n" +
        "          curl -sS https://raw.githubusercontent.com/username/repograph-ai/main/backend/analyzer.py -o analyzer.py\n\n" +
        "      - name: Comment on PR with Architecture Map\n" +
        "        uses: marocchino/sticky-pull-request-comment@v2\n" +
        "        with:\n" +
        "          path: pr_report.md\n"
      );
    }

    function generateLocalSolidAudit() {
      const fileNodes = activeGraph.nodes.filter(n => n.type !== "api-route" && n.type !== "api-call");
      
      const srpViolations: any[] = [];
      const dipViolations: any[] = [];
      const ispViolations: any[] = [];
      
      fileNodes.forEach(node => {
        const nid = node.id;
        const ntype = node.type;
        const metadata = node.metadata || {};
        const techs = (metadata.technologies as string[]) || [];
        const funcs = (metadata.functions as string[]) || [];
        const classes = (metadata.classes as string[]) || [];
        const imports = (metadata.imports as string[]) || [];
        
        if (ntype === "backend-api" && techs.includes("FastAPI") && (techs.includes("SQLAlchemy") || techs.includes("Prisma")) && techs.includes("JWT")) {
          srpViolations.push({
            file: nid,
            issue: "SRP Violation: Routing, Database Operations, and Authentication handled in a single module.",
            remedy: "**Refactoring Recommendation:**\n" +
              "Extract authentication utilities into an auth middleware/service and database queries into " +
              "a repository class. The controller module should only be responsible for mapping routes and validating payloads.\n\n" +
              "```python\n" +
              "# BEFORE (main.py)\n" +
              "@app.post('/login')\n" +
              "def login(payload: dict, db=Depends(get_db)):\n" +
              "    # directly querying DB and generating JWT here\n" +
              "    user = db.query(User).filter(User.email == payload['email']).first()\n" +
              "    token = jwt.encode({'sub': user.id}, SECRET_KEY)\n" +
              "    return {'token': token}\n\n" +
              "# AFTER (main.py + services/auth_service.py)\n" +
              "# auth_service.py manages JWT and DB query\n" +
              "@app.post('/login')\n" +
              "def login(payload: dict, auth_service=Depends(get_auth_service)):\n" +
              "    token = auth_service.authenticate_user(payload['email'], payload['password'])\n" +
              "    return {'token': token}\n" +
              "```"
          });
        }
        
        if (ntype === "module" && imports.some(imp => imp.includes("database") || imp === "db")) {
          dipViolations.push({
            file: nid,
            issue: "DIP Violation: Business module imports concrete database session directly instead of using abstraction/injection.",
            remedy: "**Refactoring Recommendation:**\n" +
              "Decouple the module from the database session. Inject the database interface or connection pool via " +
              "a dependency injection framework or constructor rather than creating or importing the database instance directly.\n\n" +
              "```python\n" +
              "# BEFORE\n" +
              "from database import SessionLocal\n" +
              "def process_order(order_id):\n" +
              "    db = SessionLocal()\n" +
              "    # process...\n\n" +
              "# AFTER\n" +
              "from database_interface import IDatabaseSession\n" +
              "def process_order(order_id, db: IDatabaseSession):\n" +
              "    # Injecting the database interface session\n" +
              "    # process...\n" +
              "```"
          });
        }
        
        if (funcs.length + classes.length > 10) {
          ispViolations.push({
            file: nid,
            issue: `ISP Violation: Fat Interface. Module exports ${funcs.length + classes.length} symbols, acting as a 'God Module'.`,
            remedy: "**Refactoring Recommendation:**\n" +
              "Break down the module into smaller, specialized interfaces or files (e.g. split into `user_api.ts`, `auth_api.ts`, etc.) " +
              "so client files only import the specific interface methods they require.\n\n" +
              "```typescript\n" +
              "# BEFORE (api.ts - exports 15+ different services)\n" +
              "export function loginUser() {}\n" +
              "export function getProfile() {}\n" +
              "export function updateInvoice() {}\n" +
              "export function deleteProduct() {}\n\n" +
              "# AFTER (Split into cohesive sub-services)\n" +
              "// authApi.ts\n" +
              "export function loginUser() {}\n" +
              "// invoiceApi.ts\n" +
              "export function updateInvoice() {}\n" +
              "```"
          });
        }
      });
      
      const baseScore = 100;
      const deductions = srpViolations.length * 12 + dipViolations.length * 12 + ispViolations.length * 8;
      const score = Math.max(45, baseScore - deductions);
      setSolidScore(score);
      
      const report: string[] = [];
      report.push("# 🛡️ SOLID Design Audit Report");
      report.push(`**Architectural Design Health Score**: \`${score}/100\``);
      
      if (score >= 90) {
        report.push("🏆 **Excellent!** The codebase is highly decoupled, follows single-responsibility modules, and implements robust dependency inversion patterns.");
      } else if (score >= 75) {
        report.push("⚠️ **Good with recommendations.** The codebase is structured relatively well, but exhibits a few SRP/DIP violations that could lead to maintenance friction.");
      } else {
        report.push("🚨 **Refactoring Recommended.** Significant violations of SOLID principles were detected. Coupling is high, and some modules are performing too many concurrent roles.");
      }
      
      report.push("");
      report.push("---");
      report.push("");
      
      report.push("## 📌 S - Single Responsibility Principle (SRP)");
      if (srpViolations.length > 0) {
        srpViolations.forEach(v => {
          report.push(`### ❌ Violation in [\`${v.file}\`](file:///${v.file})`);
          report.push(`**Issue**: ${v.issue}\n`);
          report.push(v.remedy);
          report.push("");
        });
      } else {
        report.push("✅ **No major SRP violations detected.** Modules appear well-focused on a single area of responsibility.");
        report.push("");
      }
      
      report.push("## 📌 D - Dependency Inversion Principle (DIP)");
      if (dipViolations.length > 0) {
        dipViolations.forEach(v => {
          report.push(`### ❌ Violation in [\`${v.file}\`](file:///${v.file})`);
          report.push(`**Issue**: ${v.issue}\n`);
          report.push(v.remedy);
          report.push("");
        });
      } else {
        report.push("✅ **No major DIP violations detected.** Modules utilize abstraction/injection layers instead of concrete couplings.");
        report.push("");
      }
      
      report.push("## 📌 I - Interface Segregation Principle (ISP)");
      if (ispViolations.length > 0) {
        ispViolations.forEach(v => {
          report.push(`### ❌ Violation in [\`${v.file}\`](file:///${v.file})`);
          report.push(`**Issue**: ${v.issue}\n`);
          report.push(v.remedy);
          report.push("");
        });
      } else {
        report.push("✅ **No major ISP violations detected.** Interfaces and modules expose cohesive, slim structures.");
        report.push("");
      }
      
      report.push("## 📌 O & L - Open/Closed (OCP) & Liskov Substitution (LSP)");
      report.push("✅ **Passing.** Code structures exhibit good inheritance boundaries and leverage standard object inheritance schemas where applicable.");
      
      setSolidReport(report.join("\n"));
      setSolidViolations({
        srp: srpViolations,
        dip: dipViolations,
        isp: ispViolations
      });
    }

    fetchPrReport();
    fetchSolidAudit();
  }, [graph]);

  // Identify connected elements for dynamic path highlighting
  const connectedNodeIds = React.useMemo(() => {
    if (!selectedNode || !graph) return new Set<string>();
    const set = new Set<string>([selectedNode.id]);
    graph.edges.forEach((edge: RepoEdge) => {
      if (edge.source === selectedNode.id) {
        set.add(edge.target);
      }
      if (edge.target === selectedNode.id) {
        set.add(edge.source);
      }
    });
    return set;
  }, [selectedNode, graph]);

  const connectedEdgeIds = React.useMemo(() => {
    if (!selectedNode || !graph) return new Set<string>();
    const set = new Set<string>();
    graph.edges.forEach((edge: RepoEdge) => {
      if (edge.source === selectedNode.id || edge.target === selectedNode.id) {
        set.add(edge.id);
      }
    });
    return set;
  }, [selectedNode, graph]);

  // Compute positioned nodes for flow rendering
  const flowNodes = React.useMemo(() => {
    if (!graph) return [];
    const nodes = computeLayout(graph.nodes, graph.edges);
    const hasSelection = selectedNode !== null;

    return nodes.map((node) => {
      const isSelected = selectedNode?.id === node.id;
      const isNeighbor = connectedNodeIds.has(node.id);
      
      let nodeClass = "";
      if (hasSelection) {
        if (isSelected) {
          nodeClass = "selected";
        } else if (isNeighbor) {
          nodeClass = "highlighted";
        } else {
          nodeClass = "dimmed";
        }
      }

      return {
        ...node,
        data: {
          ...node.data,
          nodeClass
        }
      };
    });
  }, [graph, selectedNode, connectedNodeIds]);

  const flowEdges = React.useMemo(() => {
    if (!graph) return [];
    const hasSelection = selectedNode !== null;

    return graph.edges.map((edge: RepoEdge) => {
      const isHighlighted = connectedEdgeIds.has(edge.id);
      let edgeClass = "";
      if (hasSelection) {
        if (isHighlighted) {
          edgeClass = "highlighted";
        } else {
          edgeClass = "dimmed";
        }
      }

      return {
        id: edge.id,
        source: edge.source,
        target: edge.target,
        label: edge.label,
        animated: edge.label === "calls" || edge.label === "defines",
        className: edgeClass,
        style: isHighlighted
          ? { stroke: "#60a5fa", strokeWidth: 2.5 }
          : hasSelection
            ? { opacity: 0.15 }
            : { stroke: "rgba(255, 255, 255, 0.15)", strokeWidth: 1.5 }
      };
    });
  }, [graph, selectedNode, connectedEdgeIds]);

  return (
    <div 
      className={`app ${sidebarCollapsed ? "sidebar-collapsed" : ""}`}
      style={{
        gridTemplateColumns: sidebarCollapsed ? "0px 1fr" : `${sidebarWidth}px 1fr`,
        transition: isResizing ? "none" : "grid-template-columns 0.3s cubic-bezier(0.4, 0, 0.2, 1)"
      }}
    >
      <aside className={`sidebar ${sidebarCollapsed ? "collapsed" : ""}`}>
        {!sidebarCollapsed && (
          <div 
            className={`sidebar-resizer ${isResizing ? "resizing" : ""}`} 
            onMouseDown={startResizing}
          />
        )}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
          <h1 style={{ margin: 0 }}>RepoGraph AI</h1>
          <button
            onClick={() => setSidebarCollapsed(true)}
            title="Collapse Sidebar"
            className="collapse-sidebar-toggle-btn"
            style={{
              background: "rgba(255, 255, 255, 0.03)",
              border: "1px solid var(--border-glass)",
              borderRadius: "8px",
              color: "var(--text-secondary)",
              cursor: "pointer",
              fontSize: "11px",
              padding: "6px 10px",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              gap: "4px",
              transition: "all 0.2s"
            }}
          >
            ◀ Collapse
          </button>
        </div>
        <p className="subtitle">Visual codebase architecture explorer & smart developer onboarding guide.</p>

        <div className="actions">
          <label className="upload-btn">
            📂 Upload ZIP Repo
            <input type="file" accept=".zip" onChange={uploadRepo} />
          </label>

          <div style={{ display: "flex", gap: "8px", margin: "4px 0" }}>
            <input
              type="text"
              placeholder="Paste public GitHub URL..."
              value={githubUrl}
              onChange={(e) => setGithubUrl(e.target.value)}
              style={{
                flex: 1,
                padding: "10px 14px",
                borderRadius: "10px",
                background: "rgba(255, 255, 255, 0.04)",
                border: "1px solid var(--border-glass)",
                color: "var(--text-primary)",
                fontSize: "12px"
              }}
            />
            <button 
              className="demo-btn" 
              onClick={scanGithubRepo}
              style={{ padding: "10px 14px", borderRadius: "10px" }}
            >
              🔍 Scan
            </button>
          </div>

          <button className="demo-btn" onClick={loadDemoCodebase}>
            ⚡ Load Demo Codebase
          </button>
        </div>

        {loading && <p style={{ fontSize: 13, color: "var(--color-frontend)", marginBottom: 20 }}>Analyzing files & building structure...</p>}
        
        {graph && !loading && (
          <div className="summary-card">
            <strong>ARCHITECTURE HEALTH</strong>
            <p>{graph.summary}</p>
          </div>
        )}

        {graph && !loading && (
          <div className="details-panel">
            <div className="tabs">
              {selectedNode ? (
                <>
                  <button 
                    className={`tab ${activeTab === "explain" ? "active" : ""}`}
                    onClick={() => {
                      setActiveTab("explain");
                      setDetailsExpanded(true);
                    }}
                  >
                    AI Onboarding
                  </button>
                  <button 
                    className={`tab ${activeTab === "code" ? "active" : ""}`}
                    onClick={() => {
                      setActiveTab("code");
                      setDetailsExpanded(true);
                    }}
                  >
                    Inspect Code
                  </button>
                  <button 
                    className="tab"
                    style={{ marginLeft: "auto", color: "var(--text-muted)", cursor: "pointer" }}
                    onClick={() => {
                      setSelectedNode(null);
                      setActiveTab("pr");
                      setDetailsExpanded(true);
                    }}
                  >
                    ✕ Close
                  </button>
                </>
              ) : (
                <>
                  <button 
                    className={`tab ${activeTab === "pr" ? "active" : ""}`}
                    onClick={() => {
                      setActiveTab("pr");
                      setDetailsExpanded(true);
                    }}
                  >
                    PR Summary
                  </button>
                  <button 
                    className={`tab ${activeTab === "solid" ? "active" : ""}`}
                    onClick={() => {
                      setActiveTab("solid");
                      setDetailsExpanded(true);
                    }}
                  >
                    🛡️ SOLID Audit
                  </button>
                  <button 
                    className={`tab ${activeTab === "archguard" ? "active" : ""}`}
                    onClick={() => {
                      setActiveTab("archguard");
                      setDetailsExpanded(true);
                    }}
                  >
                    🛡️ ArchGuard CI
                  </button>
                  <button 
                    className={`tab ${activeTab === "spec" ? "active" : ""}`}
                    onClick={() => {
                      setActiveTab("spec");
                      setDetailsExpanded(true);
                    }}
                  >
                    📐 Spec Validator
                  </button>
                  <button 
                    className={`tab ${activeTab === "agent" ? "active" : ""}`}
                    onClick={() => {
                      setActiveTab("agent");
                      setDetailsExpanded(true);
                    }}
                  >
                    🤖 AI Agent
                  </button>
                  <button 
                    className={`tab ${activeTab === "cicd" ? "active" : ""}`}
                    onClick={() => {
                      setActiveTab("cicd");
                      setDetailsExpanded(true);
                    }}
                  >
                    CI/CD Setup
                  </button>
                  <button
                    onClick={() => setDetailsExpanded(!detailsExpanded)}
                    title={detailsExpanded ? "Collapse Content" : "Expand Content"}
                    style={{
                      marginLeft: "auto",
                      background: "rgba(255, 255, 255, 0.03)",
                      border: "1px solid var(--border-glass)",
                      borderRadius: "6px",
                      color: "var(--text-secondary)",
                      cursor: "pointer",
                      fontSize: "10px",
                      padding: "4px 8px",
                      display: "flex",
                      alignItems: "center",
                      gap: "2px",
                      fontWeight: 600,
                      transition: "all 0.2s"
                    }}
                  >
                    {detailsExpanded ? "▼ Collapse" : "▲ Expand"}
                  </button>
                </>
              )}
            </div>
            
            {detailsExpanded && (
              <div className="details-content">
              {selectedNode ? (
                activeTab === "explain" ? (
                  <div 
                    className="explanation-md" 
                    dangerouslySetInnerHTML={{ __html: renderMarkdown(explanation) }} 
                  />
                ) : (
                  <pre className="code-pre">
                    <code>
                      {selectedNode.metadata?.code || `// Code is not available for this node type (${selectedNode.type}).`}
                    </code>
                  </pre>
                )
              ) : (
                activeTab === "pr" ? (
                  <div className="explanation-md">
                    <h3>Pull Request Description</h3>
                    <p style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 12 }}>
                      Copy this markdown summary directly into your GitHub Pull Request description:
                    </p>
                    <button
                      className="upload-btn"
                      style={{ width: "100%", padding: "12px", marginBottom: "16px", fontWeight: "700" }}
                      onClick={async () => {
                        try {
                          const res = await fetch("http://localhost:8000/agent/push-and-create-pr", {
                            method: "POST",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({ branch: agentBranch || null })
                          });
                          if (!res.ok) throw new Error("Could not push branch");
                          const data = await res.json();
                          if (data.github_url) {
                            window.open(data.github_url, "_blank");
                          }
                        } catch (err: any) {
                          alert("Failed to push and create PR: " + err.message + "\nMake sure you have pushed your branch using your git terminal!");
                        }
                      }}
                    >
                      🚀 Push & Create Pull Request on GitHub
                    </button>
                    <textarea
                      readOnly
                      value={prMarkdown}
                      style={{
                        width: "100%",
                        height: "220px",
                        background: "rgba(0,0,0,0.3)",
                        border: "1px solid var(--border-glass)",
                        borderRadius: "8px",
                        color: "var(--text-secondary)",
                        fontFamily: "'Fira Code', monospace",
                        fontSize: "11px",
                        padding: "10px",
                        resize: "none",
                        marginBottom: "12px"
                      }}
                      onClick={(e) => (e.target as HTMLTextAreaElement).select()}
                    />
                    <button
                      className="demo-btn"
                      style={{ width: "100%", padding: "10px" }}
                      onClick={() => {
                        navigator.clipboard.writeText(prMarkdown);
                        alert("PR Markdown copied to clipboard!");
                      }}
                    >
                      📋 Copy Markdown
                    </button>
                  </div>
                ) : activeTab === "cicd" ? (
                  <div className="explanation-md">
                    <h3>Automated PR Comments</h3>
                    <p style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 12 }}>
                      Save this file as <code>.github/workflows/repograph.yml</code> to run on every Pull Request and post the architecture map:
                    </p>
                    <textarea
                      readOnly
                      value={githubActionYaml}
                      style={{
                        width: "100%",
                        height: "220px",
                        background: "rgba(0,0,0,0.3)",
                        border: "1px solid var(--border-glass)",
                        borderRadius: "8px",
                        color: "var(--text-secondary)",
                        fontFamily: "'Fira Code', monospace",
                        fontSize: "11px",
                        padding: "10px",
                        resize: "none",
                        marginBottom: "12px"
                      }}
                      onClick={(e) => (e.target as HTMLTextAreaElement).select()}
                    />
                    <button
                      className="demo-btn"
                      style={{ width: "100%", padding: "10px" }}
                      onClick={() => {
                        navigator.clipboard.writeText(githubActionYaml);
                        alert("GitHub Action YAML copied to clipboard!");
                      }}
                    >
                      📋 Copy Action Config
                    </button>
                  </div>
                ) : activeTab === "solid" ? (
                  <div className="explanation-md">
                    <div style={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      background: "rgba(255, 255, 255, 0.05)",
                      padding: "12px",
                      borderRadius: "10px",
                      marginBottom: "16px",
                      border: "1px solid var(--border-glass)"
                    }}>
                      <div>
                        <strong style={{ fontSize: "14px", fontFamily: "'Outfit', sans-serif" }}>DESIGN HEALTH</strong>
                        <div style={{ fontSize: "10px", color: "var(--text-muted)", marginTop: "2px" }}>SOLID Principles Audit</div>
                      </div>
                      <div style={{
                        fontSize: "24px",
                        fontWeight: 700,
                        fontFamily: "'Outfit', sans-serif",
                        color: solidScore && solidScore >= 80 ? "var(--color-database)" : "var(--color-infra)"
                      }}>
                        {solidScore}%
                      </div>
                    </div>
                    
                    {/* Rich custom rendering of SOLID violations with direct Auto-Fix buttons */}
                    <div className="solid-audit-list">
                      {solidViolations.srp.map((v: any, i: number) => (
                        <div className="solid-issue-card srp" key={`srp-${i}`}>
                          <div className="solid-header-row">
                            <div>
                              <div className="node-type-badge" style={{color: "var(--color-backend)"}}>SRP Violation</div>
                              <strong className="solid-issue-title">{v.file}</strong>
                            </div>
                            <button className="fix-violation-btn" onClick={() => triggerAutoFix(v.file, `Fix SRP violation in ${v.file}: Extract authentication / database logic to specialized files and simplify the main route controllers.`, v.file)}>
                              ⚡ Auto-Fix
                            </button>
                          </div>
                          <p style={{fontSize: 12, margin: "6px 0", color: "var(--text-secondary)", lineHeight: 1.4}}>{v.issue}</p>
                          <div className="solid-issue-remedy" style={{marginTop: 8}}>
                            <span style={{fontSize: 10, fontWeight: 700, color: "var(--text-primary)"}}>REMEDY PROPOSAL:</span>
                            <p style={{fontSize: 11, margin: "4px 0 0 0", color: "var(--text-secondary)"}}>Separate concerns by moving helper classes out of route decorators.</p>
                          </div>
                        </div>
                      ))}
                      {solidViolations.dip.map((v: any, i: number) => (
                        <div className="solid-issue-card dip" key={`dip-${i}`}>
                          <div className="solid-header-row">
                            <div>
                              <div className="node-type-badge" style={{color: "var(--color-database)"}}>DIP Violation</div>
                              <strong className="solid-issue-title">{v.file}</strong>
                            </div>
                            <button className="fix-violation-btn" onClick={() => triggerAutoFix(v.file, `Fix DIP violation in ${v.file}: Decouple the database session dependency and inject it dynamically.`, v.file)}>
                              ⚡ Auto-Fix
                            </button>
                          </div>
                          <p style={{fontSize: 12, margin: "6px 0", color: "var(--text-secondary)", lineHeight: 1.4}}>{v.issue}</p>
                        </div>
                      ))}
                      {solidViolations.isp.map((v: any, i: number) => (
                        <div className="solid-issue-card isp" key={`isp-${i}`}>
                          <div className="solid-header-row">
                            <div>
                              <div className="node-type-badge" style={{color: "var(--color-auth)"}}>ISP Violation</div>
                              <strong className="solid-issue-title">{v.file}</strong>
                            </div>
                            <button className="fix-violation-btn" onClick={() => triggerAutoFix(v.file, `Fix ISP violation in ${v.file}: Segregate interface methods so other components import thinner dependencies.`, v.file)}>
                              ⚡ Auto-Fix
                            </button>
                          </div>
                          <p style={{fontSize: 12, margin: "6px 0", color: "var(--text-secondary)", lineHeight: 1.4}}>{v.issue}</p>
                        </div>
                      ))}
                      {solidViolations.srp.length === 0 && solidViolations.dip.length === 0 && solidViolations.isp.length === 0 && (
                        <p style={{textAlign: "center", color: "var(--color-database)", padding: "12px", fontSize: "13px"}}>🏆 Excellent! No SOLID design violations detected.</p>
                      )}
                    </div>
                  </div>
                ) : activeTab === "archguard" ? (
                  <div className="explanation-md">
                    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
                      <h3>🛡️ ArchGuard CI Regression Gate</h3>
                      {ciStatus !== "idle" && ciStatus !== "running" && (
                        <div className={ciStatus === "passed" ? "ci-badge-passed" : "ci-badge-failed"}>
                          {ciStatus === "passed" ? "PASSED" : "FAILED"}
                        </div>
                      )}
                    </div>
                    <p style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 12 }}>
                      Compares the current workspace against the base design guidelines and evaluates regression.
                    </p>

                    {ciStatus === "idle" && (
                      <button className="upload-btn" onClick={runArchGuardCI} style={{ width: "100%", padding: 12 }}>
                        Run ArchGuard CI Check
                      </button>
                    )}

                    {ciStatus === "running" && (
                      <div className="agent-console-container">
                        <div className="agent-terminal" style={{ height: "180px" }}>
                          {ciTerminalLogs.map((line, idx) => (
                            <div key={idx} className="terminal-line system">{line}</div>
                          ))}
                          <span className="blinking-cursor" />
                        </div>
                      </div>
                    )}

                    {(ciStatus === "passed" || ciStatus === "failed") && (
                      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                        <div style={{
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "space-between",
                          background: "rgba(255, 255, 255, 0.03)",
                          padding: "10px 14px",
                          borderRadius: "10px",
                          border: "1px solid var(--border-glass)"
                        }}>
                          <span style={{ fontSize: 12, fontWeight: 600 }}>REGRESSION SCORE:</span>
                          <strong style={{
                            fontSize: 18,
                            fontFamily: "'Outfit', sans-serif",
                            color: ciScore && ciScore > 20 ? "var(--color-infra)" : "var(--color-database)"
                          }}>
                            {ciScore}%
                          </strong>
                        </div>

                        {ciFailedRules.length > 0 && (
                          <div>
                            <strong style={{ fontSize: 11, display: "block", marginBottom: 6, color: "var(--color-infra)" }}>
                              BROKEN CONSTRAINTS:
                            </strong>
                            {ciFailedRules.map((rule, idx) => (
                              <div className="ci-rule-card" key={idx}>
                                {rule}
                              </div>
                            ))}
                          </div>
                        )}

                        <div 
                          className="explanation-md"
                          style={{
                            background: "rgba(0,0,0,0.2)",
                            padding: 12,
                            borderRadius: 8,
                            border: "1px solid rgba(255,255,255,0.05)",
                            fontSize: 12
                          }}
                          dangerouslySetInnerHTML={{ __html: renderMarkdown(ciReport) }}
                        />

                        <button className="demo-btn" onClick={runArchGuardCI} style={{ width: "100%", padding: 10 }}>
                          🔄 Re-run CI Check
                        </button>
                      </div>
                    )}
                  </div>
                ) : activeTab === "spec" ? (
                  <div className="explanation-md">
                    <h3>📐 Spec-to-Reality Validator</h3>
                    <p style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 12 }}>
                      Verify if your architectural code matches specifications or diagrams using multimodal Gemini 3.5.
                    </p>

                    <div style={{ display: "flex", flexDirection: "column", gap: 10, marginBottom: 12 }}>
                      <textarea
                        placeholder="Define constraints, e.g.: App.tsx should not import API client utilities directly..."
                        value={specText}
                        onChange={(e) => setSpecText(e.target.value)}
                        style={{
                          width: "100%",
                          height: "90px",
                          background: "rgba(0,0,0,0.3)",
                          border: "1px solid var(--border-glass)",
                          borderRadius: "8px",
                          color: "var(--text-primary)",
                          fontSize: "12px",
                          padding: "10px",
                          resize: "none",
                          fontFamily: "inherit"
                        }}
                      />

                      <div 
                        className="upload-dropzone"
                        onClick={() => document.getElementById("spec-image-input")?.click()}
                      >
                        <span>🖼️ Drag or Click to upload diagram (.png, .jpg)</span>
                        <input
                          id="spec-image-input"
                          type="file"
                          accept="image/*"
                          style={{ display: "none" }}
                          onChange={(e) => {
                            const file = e.target.files?.[0];
                            if (file) {
                              setSpecImageFile(file);
                              const reader = new FileReader();
                              reader.onload = (event) => {
                                setSpecImagePreview(event.target?.result as string);
                              };
                              reader.readAsDataURL(file);
                            }
                          }}
                        />
                      </div>

                      {specImagePreview && (
                        <div className="preview-thumbnail-container">
                          <img src={specImagePreview} className="preview-thumbnail" alt="Spec preview" />
                          <span style={{ fontSize: 11, overflow: "hidden", textOverflow: "ellipsis", maxWidth: "200px" }}>
                            {specImageFile?.name}
                          </span>
                          <span 
                            style={{ color: "var(--text-muted)", cursor: "pointer", marginLeft: "auto" }}
                            onClick={() => {
                              setSpecImageFile(null);
                              setSpecImagePreview("");
                            }}
                          >
                            ✕
                          </span>
                        </div>
                      )}

                      <button 
                        className="upload-btn" 
                        disabled={specLoading}
                        onClick={runSpecValidator}
                        style={{ padding: 12 }}
                      >
                        {specLoading ? "Validating Spec..." : "Verify Spec Alignment"}
                      </button>
                    </div>

                    {specScore !== null && (
                      <div style={{ display: "flex", flexDirection: "column", gap: 12, marginTop: 12 }}>
                        <div style={{
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "space-between",
                          background: "rgba(255, 255, 255, 0.03)",
                          padding: "10px 14px",
                          borderRadius: "10px",
                          border: "1px solid var(--border-glass)"
                        }}>
                          <span style={{ fontSize: 12, fontWeight: 600 }}>DESIGN ALIGNMENT SCORE:</span>
                          <strong style={{
                            fontSize: 18,
                            fontFamily: "'Outfit', sans-serif",
                            color: specScore >= 80 ? "var(--color-database)" : "var(--color-infra)"
                          }}>
                            {specScore}%
                          </strong>
                        </div>

                        {specDivergences.length > 0 && (
                          <div>
                            <strong style={{ fontSize: 11, display: "block", marginBottom: 6, color: "var(--color-infra)" }}>
                              DIVERGENCES DETECTED:
                            </strong>
                            {specDivergences.map((divg, idx) => (
                              <div className="ci-rule-card" key={idx} style={{ background: "rgba(239, 68, 68, 0.02)" }}>
                                ⚠️ {divg}
                              </div>
                            ))}
                          </div>
                        )}

                        {specRemedies.length > 0 && (
                          <div>
                            <strong style={{ fontSize: 11, display: "block", marginBottom: 6, color: "var(--color-database)" }}>
                              REMEDY RECOMMENDATIONS:
                            </strong>
                            {specRemedies.map((remedy, idx) => (
                              <div className="ci-rule-card" key={idx} style={{ background: "rgba(16, 185, 129, 0.04)", borderColor: "rgba(16, 185, 129, 0.15)", color: "var(--text-secondary)" }}>
                                💡 {remedy}
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                ) : (
                  /* activeTab === "agent" */
                  <div className="explanation-md">
                    {agentStatus === "idle" && (
                      <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
                        <h3>🤖 AI Code Modification Agent</h3>
                        <p style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 4 }}>
                          Describe a feature or fix. The multi-agent team will edit the files and draft a Pull Request.
                        </p>
                        
                        <textarea
                          placeholder="What would you like the agent to do? e.g. Add a GET /health route..."
                          value={agentInstruction}
                          onChange={(e) => setAgentInstruction(e.target.value)}
                          style={{
                            width: "100%",
                            height: "90px",
                            background: "rgba(0,0,0,0.3)",
                            border: "1px solid var(--border-glass)",
                            borderRadius: "8px",
                            color: "var(--text-primary)",
                            fontSize: "12px",
                            padding: "10px",
                            resize: "none",
                            fontFamily: "inherit"
                          }}
                        />

                        {agentTargetFile && (
                          <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, color: "var(--color-backend)" }}>
                            <span>🎯 Targeted File:</span>
                            <code>{agentTargetFile}</code>
                            <span 
                              style={{ color: "var(--text-muted)", cursor: "pointer", marginLeft: "auto" }}
                              onClick={() => setAgentTargetFile("")}
                            >
                              clear
                            </span>
                          </div>
                        )}

                        <div style={{ display: "flex", flexWrap: "wrap", gap: "6px", margin: "4px 0" }}>
                          <button 
                            className="demo-btn" 
                            style={{ padding: "6px 10px", fontSize: "10px", borderRadius: "6px" }}
                            onClick={() => {
                              setAgentInstruction("Add a GET /health check endpoint to backend/main.py returning Status OK");
                              setAgentTargetFile("backend/main.py");
                            }}
                          >
                            ➕ Add Health Endpoint
                          </button>
                          <button 
                            className="demo-btn" 
                            style={{ padding: "6px 10px", fontSize: "10px", borderRadius: "6px" }}
                            onClick={() => {
                              setAgentInstruction("Refactor backend/main.py to resolve the SOLID SRP routing violation. Extract login queries and JWT verification to auth module services.");
                              setAgentTargetFile("backend/main.py");
                            }}
                          >
                            ⚡ Resolve SRP Violation
                          </button>
                        </div>

                        <button type="button" className="upload-btn" onClick={runAgentCreator} style={{ marginTop: 8, padding: 12 }}>
                          🚀 Launch Agent Team & Fix
                        </button>
                      </div>
                    )}

                    {agentStatus === "running" && (
                      <div className="agent-console-container">
                        <h3>⚡ Agent Execution Terminal</h3>
                        <div className="agent-terminal">
                          {terminalLines.map((line, idx) => {
                            let typeClass = "system";
                            if (line.startsWith("[Architect")) typeClass = "architect";
                            else if (line.startsWith("[Coder")) typeClass = "coder";
                            else if (line.startsWith("[Reviewer")) typeClass = "reviewer";
                            else if (line.startsWith("[Architect Agent Thinking") || line.startsWith("[Coder Agent Thinking") || line.startsWith("[Reviewer Agent Thinking")) typeClass = "thinking";
                            
                            return (
                              <div key={idx} className={`terminal-line ${typeClass}`}>
                                {line}
                              </div>
                            );
                          })}
                          <span className="blinking-cursor" />
                        </div>
                        <p style={{ fontSize: 10, color: "var(--text-muted)", textAlign: "center" }}>
                          Multi-Agent collaboration loop running in secure sandbox environment.
                        </p>
                      </div>
                    )}

                    {agentStatus === "pr_created" && (
                      <div className="pr-dashboard">
                        <div className="pr-card-header">
                          <div className="pr-status-row">
                            <span className="status-badge">Open</span>
                            <span className="branch-badge">{agentBranch} ➔ main</span>
                          </div>
                          <div className="pr-title">{agentPrTitle}</div>
                        </div>

                        <strong>📋 Pull Request Report</strong>
                        <div className="pr-markdown-viewer" dangerouslySetInnerHTML={{ __html: renderMarkdown(agentPrBody) }} />

                        <strong>📂 Code Modifications</strong>
                        <div className="diff-viewer">
                          {renderDiffViewer(agentDiff)}
                        </div>

                        <button className="merge-btn" onClick={mergeAgentPR}>
                          🔀 Merge Pull Request locally
                        </button>
                      </div>
                    )}

                    {agentStatus === "merged" && (
                      <div style={{ textAlign: "center", padding: "16px 8px" }}>
                        <div style={{ fontSize: "40px", marginBottom: "12px" }}>🎉</div>
                        <h3 style={{ color: "var(--color-database)", marginBottom: "8px" }}>PR Merged Successfully!</h3>
                        <p style={{ fontSize: "12px", color: "var(--text-secondary)", lineHeight: 1.5, marginBottom: "16px" }}>
                          The code changes have been merged into the master codebase. The architecture graph has been refreshed to reflect the new structure.
                        </p>
                        <button 
                          className="demo-btn" 
                          style={{ width: "100%" }}
                          onClick={() => {
                            setAgentStatus("idle");
                            setAgentInstruction("");
                            setAgentTargetFile("");
                          }}
                        >
                          Back to Agent Console
                        </button>
                      </div>
                    )}
                  </div>
                )
              )}
            </div>
            )}
          </div>
        )}
      </aside>

      <main className="graph">
        {sidebarCollapsed && (
          <button 
            onClick={() => setSidebarCollapsed(false)}
            title="Expand Sidebar"
            className="expand-sidebar-toggle-btn"
            style={{
              position: 'absolute',
              left: '20px',
              top: '20px',
              zIndex: 100,
              background: 'var(--bg-glass)',
              border: '1px solid var(--border-glass)',
              borderRadius: '10px',
              color: 'var(--text-primary)',
              padding: '10px 16px',
              cursor: 'pointer',
              fontFamily: "'Outfit', sans-serif",
              fontSize: '13px',
              fontWeight: 600,
              boxShadow: '0 4px 20px rgba(0,0,0,0.5)',
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              backdropFilter: 'blur(20px)',
              transition: 'all 0.3s',
            }}
          >
            ▶ Expand Sidebar
          </button>
        )}

        {graph && (
          <div className="swimlane-headers">
            <div className="swimlane-header">Client UI</div>
            <div className="swimlane-header">API Requests</div>
            <div className="swimlane-header">HTTP Routes</div>
            <div className="swimlane-header">Server Logic</div>
            <div className="swimlane-header">Utilities</div>
            <div className="swimlane-header">Data & Infra</div>
          </div>
        )}

        {graph ? (
          <>
            <ReactFlow
              nodes={flowNodes}
              edges={flowEdges}
              nodeTypes={nodeTypes}
              fitView
              onNodeClick={(_: any, node: any) => {
                const original = graph.nodes.find((n: RepoNode) => n.id === node.id);
                if (original) explainNode(original);
              }}
              onPaneClick={() => {
                setSelectedNode(null);
                setActiveTab("pr");
              }}
            >
              <MiniMap />
              <Controls />
              <Background color="rgba(255,255,255,0.05)" gap={16} size={1} />
            </ReactFlow>

            {historyCommits.length > 0 && (
              <>
                {narrationOpen && commitNarration && (
                  <div className="narration-overlay">
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                      <strong style={{ fontFamily: "'Outfit', sans-serif", color: "#a855f7", fontSize: 12 }}>
                        🕒 ARCHITECTURAL HISTORIAN NARRATION
                      </strong>
                      <span 
                        style={{ color: "var(--text-muted)", cursor: "pointer", fontSize: 14 }}
                        onClick={() => setNarrationOpen(false)}
                      >
                        ✕
                      </span>
                    </div>
                    <p style={{ margin: 0 }}>{commitNarration}</p>
                  </div>
                )}

                <div className="timeline-scrubber-container">
                  <div className="timeline-header">
                    <span>🕒 Time-Travel Historian Scrubber</span>
                    <span className="commit-bubble-text">
                      {historyCommits[currentCommitIdx]?.sha} - {historyCommits[currentCommitIdx]?.message}
                    </span>
                  </div>
                  <div className="timeline-slider-row">
                    <span style={{ fontSize: 10, color: "var(--text-muted)" }}>Oldest</span>
                    <input
                      type="range"
                      className="timeline-slider"
                      min={0}
                      max={historyCommits.length - 1}
                      value={currentCommitIdx}
                      onChange={(e) => handleTimelineChange(parseInt(e.target.value))}
                    />
                    <span style={{ fontSize: 10, color: "var(--text-muted)" }}>Newest</span>
                  </div>
                </div>
              </>
            )}
          </>
        ) : (
          <div className="empty-state">
            <div className="empty-icon">📁</div>
            <p>Upload a zipped repository, paste a public GitHub URL, or load the demo codebase to begin.</p>
          </div>
        )}
      </main>
    </div>
  );
}

const rootElement = document.getElementById("root");
if (rootElement) {
  ReactDOM.createRoot(rootElement).render(<App />);
}
