#!/usr/bin/env python3
import sys
import json
import traceback
from pathlib import Path

# Setup Python paths to import analyzer
CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent
sys.path.append(str(CURRENT_DIR))

from analyzer import (
    run_archguard_ci_agent,
    run_spec_validator_agent,
    checkout_commit_and_map,
    run_multi_agent_flow,
    run_codebase_tour_guide_agent,
    run_agentic_solid_audit_agent
)

def send_response(data):
    """Writes a JSON-RPC response frame to stdout followed by a newline."""
    sys.stdout.write(json.dumps(data) + "\n")
    sys.stdout.flush()

def log_stderr(message):
    """Logs debugging details safely to stderr (stdout is reserved for JSON-RPC)."""
    sys.stderr.write(f"[MCP Server] {message}\n")
    sys.stderr.flush()

def main():
    log_stderr("Starting RepoGraph AI MCP Stdio Server...")
    
    while True:
        line = sys.stdin.readline()
        if not line:
            break
        
        try:
            req = json.loads(line.strip())
            if not isinstance(req, dict):
                continue
                
            method = req.get("method")
            req_id = req.get("id")
            
            if method == "initialize":
                res = {
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
                send_response(res)
                log_stderr("MCP initialized successfully.")
                
            elif method == "tools/list":
                res = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "tools": [
                            {
                                "name": "run_archguard_ci",
                                "description": "Compares base master/main branch vs current branch to check architectural regressions & SOLID compliance.",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {
                                        "branch": {
                                            "type": "string",
                                            "description": "The branch to check regression against (default: 'main')."
                                        }
                                    },
                                    "required": []
                                }
                            },
                            {
                                "name": "validate_spec",
                                "description": "Compares architectural specifications (and optional graphic block diagrams) against actual graph code connections using Gemini Multimodal vision.",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {
                                        "spec_text": {
                                            "type": "string",
                                            "description": "Design rules and specification directives."
                                        },
                                        "image_path": {
                                            "type": "string",
                                            "description": "Optional absolute file path to a layout diagram image (.png or .jpg)."
                                        }
                                    },
                                    "required": ["spec_text"]
                                }
                            },
                            {
                                "name": "time_travel",
                                "description": "Checks out a specific commit sha, maps the graph structure, and narratively describes evolution of design debt or modular improvement.",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {
                                        "sha": {
                                            "type": "string",
                                            "description": "Commit SHA hash to scan and narrate."
                                        }
                                    },
                                    "required": ["sha"]
                                }
                            },
                            {
                                "name": "codebase_agent_fix",
                                "description": "Launches the autonomous multi-agent developer crew to implement modifications, execute syntax verification checks, and draft GitHub-ready descriptions.",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {
                                        "instruction": {
                                            "type": "string",
                                            "description": "Goal modification instruction for the agentic dev team."
                                        },
                                        "target_file": {
                                            "type": "string",
                                            "description": "Optional target file name to scope edits."
                                        }
                                    },
                                    "required": ["instruction"]
                                }
                            },
                            {
                                "name": "codebase_tour_guide",
                                "description": "Acts as an onboarding tour guide copilot. Traces call dependencies and visually explains repository dynamics for a specific question.",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {
                                        "query": {
                                            "type": "string",
                                            "description": "User onboarding or architecture inquiry."
                                        }
                                    },
                                    "required": ["query"]
                                }
                            },
                            {
                                "name": "agentic_solid_audit",
                                "description": "Triggers a deep LLM-based SOLID principles architectural health audit across the active repository.",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {},
                                    "required": []
                                }
                            }
                        ]
                    }
                }
                send_response(res)
                
            elif method == "tools/call":
                params = req.get("params", {})
                tool_name = params.get("name")
                args = params.get("arguments", {})
                
                log_stderr(f"Tool execution requested: {tool_name} with args {args}")
                tool_result_text = ""
                
                try:
                    if tool_name == "run_archguard_ci":
                        branch = args.get("branch", "main")
                        res_data = run_archguard_ci_agent(str(PROJECT_ROOT), branch)
                        tool_result_text = (
                            f"ArchGuard CI Regression Audit for branch: {branch}\n"
                            f"Regression Score: {res_data.get('regression_score')}%\n"
                            f"Passed: {res_data.get('passed')}\n"
                            f"Broken Constraints: {', '.join(res_data.get('failed_rules', [])) or 'None'}\n\n"
                            f"Diff Report:\n{res_data.get('diff_markdown')}"
                        )
                        
                    elif tool_name == "validate_spec":
                        spec_text = args.get("spec_text")
                        image_path = args.get("image_path")
                        image_bytes = None
                        
                        if image_path:
                            try:
                                path_obj = Path(image_path)
                                if path_obj.exists():
                                    image_bytes = path_obj.read_bytes()
                                    log_stderr(f"Loaded multimodal visual spec bytes from {image_path}")
                                else:
                                    log_stderr(f"Warning: diagram image path not found: {image_path}")
                            except Exception as img_err:
                                log_stderr(f"Failed to read image bytes: {img_err}")
                                
                        res_data = run_spec_validator_agent(str(PROJECT_ROOT), spec_text, image_bytes)
                        tool_result_text = (
                            f"Spec Alignment Audit Score: {res_data.get('score')}%\n"
                            f"Divergences: {res_data.get('divergences')}\n"
                            f"Proposed Remedies: {res_data.get('remedy_proposals')}"
                        )
                        
                    elif tool_name == "time_travel":
                        sha = args.get("sha")
                        res_data = checkout_commit_and_map(str(PROJECT_ROOT), sha)
                        tool_result_text = (
                            f"Checked out Commit SHA: {sha}\n"
                            f"Evolution Narration:\n{res_data.get('narration')}\n\n"
                            f"Active components mapped in graph: {len(res_data.get('graph', {}).get('nodes', []))}"
                        )
                        
                    elif tool_name == "codebase_agent_fix":
                        instruction = args.get("instruction")
                        target_file = args.get("target_file")
                        
                        res_data = run_multi_agent_flow(str(PROJECT_ROOT), instruction, target_file)
                        tool_result_text = (
                            f"AI Agent Modification completed.\n"
                            f"PR Branch name: {res_data.get('branch')}\n"
                            f"Title: {res_data.get('pr_title')}\n"
                            f"Description:\n{res_data.get('pr_body')}\n\n"
                            f"Code Diffs:\n{res_data.get('diff')}"
                        )
                        
                    elif tool_name == "codebase_tour_guide":
                        query_val = args.get("query")
                        res_data = run_codebase_tour_guide_agent(str(PROJECT_ROOT), query_val)
                        tool_result_text = (
                            f"🗺️ Codebase Tour Guide Onboarding report:\n\n"
                            f"{res_data}"
                        )
                        
                    elif tool_name == "agentic_solid_audit":
                        res_data = run_agentic_solid_audit_agent(str(PROJECT_ROOT))
                        tool_result_text = (
                            f"🛡️ Agentic SOLID Architectural Health Audit:\n"
                            f"Audit Score: {res_data.get('score')}%\n\n"
                            f"Executive Summary:\n{res_data.get('report')}\n\n"
                            f"SRP Violations: {res_data.get('srp_violations', []) or res_data.get('srp', [])}\n"
                            f"DIP Violations: {res_data.get('dip_violations', []) or res_data.get('dip', [])}\n"
                            f"ISP Violations: {res_data.get('isp_violations', []) or res_data.get('isp', [])}\n"
                            f"Remedy Actions: {res_data.get('proposed_remedies', [])}"
                        )
                    else:
                        raise ValueError(f"Unknown tool name: {tool_name}")
                        
                    res = {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {
                            "content": [
                                {
                                    "type": "text",
                                    "text": tool_result_text
                                }
                            ]
                        }
                    }
                    send_response(res)
                    
                except Exception as eval_exc:
                    log_stderr(f"Tool execution failed: {eval_exc}\n{traceback.format_exc()}")
                    res = {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "error": {
                            "code": -32603,
                            "message": str(eval_exc),
                            "data": traceback.format_exc()
                        }
                    }
                    send_response(res)
            else:
                log_stderr(f"Ignored request method: {method}")
                
        except Exception as exc:
            log_stderr(f"Invalid frame request: {exc}\n{traceback.format_exc()}")
            
if __name__ == "__main__":
    main()
