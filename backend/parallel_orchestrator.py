#!/usr/bin/env python3
import sys
import os
import json
import concurrent.futures
from pathlib import Path
from typing import List

# Setup Python paths to import analyzer
CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent
sys.path.append(str(CURRENT_DIR))

from google import genai
from google.genai import types

from analyzer import (
    run_archguard_ci_agent,
    run_spec_validator_agent,
    checkout_commit_and_map,
    get_gemini_client
)

# ----------------- Python Function Tool Definitions -----------------

def run_archguard_ci(branch: str = "main") -> str:
    """Compares base master/main branch vs current branch to check architectural regressions & SOLID compliance.
    
    Args:
        branch: The target branch to compare design rules against.
    """
    print(f"\n[Tool Execution] 🛡️ Running ArchGuard CI Check on branch '{branch}'...")
    res = run_archguard_ci_agent(str(PROJECT_ROOT), branch)
    output = (
        f"ArchGuard CI check outcome:\n"
        f"Regression Score: {res.get('regression_score')}%\n"
        f"Passed Gate: {res.get('passed')}\n"
        f"Divergences: {res.get('failed_rules')}\n"
        f"Report Summary:\n{res.get('diff_markdown')}\n"
    )
    print(f"[Tool Execution] 🛡️ ArchGuard CI completed.")
    return output

def validate_spec(spec_text: str) -> str:
    """Compares codebase specifications against actual modular graph structures.
    
    Args:
        spec_text: Text specifying design rules or file dependencies.
    """
    print(f"\n[Tool Execution] 📐 Running Spec-to-Reality Validator on: '{spec_text}'...")
    res = run_spec_validator_agent(str(PROJECT_ROOT), spec_text, None)
    output = (
        f"Spec-to-Reality Validation:\n"
        f"Alignment Score: {res.get('score')}%\n"
        f"Detected Divergences: {res.get('divergences')}\n"
        f"Actionable Fixes: {res.get('remedy_proposals')}\n"
    )
    print(f"[Tool Execution] 📐 Spec Validator completed.")
    return output

def time_travel(sha: str) -> str:
    """Checks out a specific commit sha, maps the architecture graph, and narratively describes code evolution.
    
    Args:
        sha: Git commit SHA to scan and narrate.
    """
    print(f"\n[Tool Execution] 🕒 Running Time-Travel Scrubber on Commit: '{sha}'...")
    res = checkout_commit_and_map(str(PROJECT_ROOT), sha)
    output = (
        f"Git Scrubber at {sha}:\n"
        f"Code Evolution Narration: {res.get('narration')}\n"
    )
    print(f"[Tool Execution] 🕒 Time-Travel Scrubber completed.")
    return output

# ----------------- Orchestration Execution Flow -----------------

def run_orchestrated_parallel_flow(user_query: str):
    print("=" * 70)
    print(f"🔮 REPO-GRAPH AI PARALLEL AGENT ORCHESTRATOR")
    print(f"Prompt: '{user_query}'")
    print("=" * 70)
    
    client = get_gemini_client()
    
    # 1. Fallback Simulation if API key is not configured
    if not client:
        print("[System] GEMINI_API_KEY not configured. Running High-Fidelity Parallel Simulation...\n")
        
        # Decide which tools are relevant based on query words
        query_lower = user_query.lower()
        futures = []
        
        with concurrent.futures.ThreadPoolExecutor() as executor:
            if "ci" in query_lower or "branch" in query_lower or "regression" in query_lower:
                futures.append(executor.submit(run_archguard_ci, "main"))
            if "spec" in query_lower or "depend" in query_lower or "should" in query_lower:
                futures.append(executor.submit(validate_spec, "App.tsx should not import API client directly"))
            if "commit" in query_lower or "history" in query_lower or "travel" in query_lower:
                futures.append(executor.submit(time_travel, "07dfa07"))
                
            # If nothing specific was found, run both CI and Spec by default
            if not futures:
                futures.append(executor.submit(run_archguard_ci, "main"))
                futures.append(executor.submit(validate_spec, "backend/main.py must decouple models"))
                
        results = [f.result() for f in futures]
        
        print("\n" + "=" * 70)
        print("💡 ORCHESTRATOR REPORT SUMMARY (MOCK FALLBACK)")
        print("=" * 70)
        for r in results:
            print(r)
            print("-" * 50)
        return

    # 2. Authentic Gemini Parallel Tool Calling Flow
    try:
        tools_list = [run_archguard_ci, validate_spec, time_travel]
        config = types.GenerateContentConfig(
            tools=tools_list,
            temperature=0.1
        )
        
        print("[System] Launching Gemini 3.5 model turn...")
        response = client.models.generate_content(
            model="gemini-3.5-flash",
            contents=user_query,
            config=config
        )
        
        # Check if the model generated function calls
        function_calls = response.function_calls
        if not function_calls:
            print("\n[System] Gemini resolved the query directly without requiring tool calls:")
            print(response.text)
            return
            
        print(f"\n⚡ Gemini requested {len(function_calls)} PARALLEL Tool Calls:")
        for fc in function_calls:
            print(f"  ➜ Call '{fc.name}' with arguments: {fc.args}")
            
        # Concurrently execute functions
        tool_outputs = {}
        
        def execute_call(fc):
            try:
                name = fc.name
                args = fc.args
                if name == "run_archguard_ci":
                    res = run_archguard_ci(**args)
                elif name == "validate_spec":
                    res = validate_spec(**args)
                elif name == "time_travel":
                    res = time_travel(**args)
                else:
                    res = f"Error: Unknown tool {name}"
                return fc.name, res
            except Exception as e:
                return fc.name, f"Error executing tool {fc.name}: {str(e)}"

        with concurrent.futures.ThreadPoolExecutor() as executor:
            futures = [executor.submit(execute_call, fc) for fc in function_calls]
            for f in concurrent.futures.as_completed(futures):
                name, output = f.result()
                tool_outputs[name] = output

        # Supply tool execution content parts back to Gemini in next turn
        tool_responses = []
        for fc in function_calls:
            name = fc.name
            result_val = tool_outputs.get(name, "No response")
            tool_responses.append(
                types.Part.from_function_response(
                    name=name,
                    response={"result": result_val}
                )
            )
            
        print("\n[System] Sending tool responses back to Gemini for compilation...")
        contents = [
            types.Content(role="user", parts=[types.Part.from_text(text=user_query)]),
            response.candidates[0].content,  # Model's tools request turn
            types.Content(role="user", parts=tool_responses)  # User's response turn
        ]
        
        final_response = client.models.generate_content(
            model="gemini-3.5-flash",
            contents=contents,
            config=config
        )
        
        print("\n" + "=" * 70)
        print("💡 ORCHESTRATOR COHESIVE SYSTEM REPORT")
        print("=" * 70)
        print(final_response.text)
        print("=" * 70)
        
    except Exception as exc:
        print(f"\n[System Error] Orchestrator execution crashed: {exc}")

if __name__ == "__main__":
    query = "Run architectural CI verification checks and evaluate spec requirements 'backend/main.py must be decoupled from models'"
    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
    run_orchestrated_parallel_flow(query)
