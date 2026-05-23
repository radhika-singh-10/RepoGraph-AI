from pydantic import BaseModel
from typing import Any, Dict, List, Optional

class GraphNode(BaseModel):
    id: str
    label: str
    type: str
    metadata: Dict[str, Any] = {}

class GraphEdge(BaseModel):
    id: str
    source: str
    target: str
    label: str

class RepoGraph(BaseModel):
    nodes: List[GraphNode]
    edges: List[GraphEdge]
    summary: str

class ExplainRequest(BaseModel):
    node_id: str
    graph: RepoGraph
