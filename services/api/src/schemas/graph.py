from typing import List, Dict, Any, Optional
from pydantic import BaseModel

class GraphNode(BaseModel):
    id: str
    label: str # Disease, Medication, SideEffect
    properties: Dict[str, Any]

class GraphEdge(BaseModel):
    id: str
    source: str
    target: str
    type: str # HAS_DIAGNOSIS, RECEIVED, OBSERVED_WITH, CO_OCCURS_WITH
    properties: Dict[str, Any]

class GraphDataOut(BaseModel):
    nodes: List[GraphNode]
    edges: List[GraphEdge]
    disclaimer: str = "Associations represent synthetic observed co-occurrences, not proven pharmacological causation."

class GraphSyncStatusOut(BaseModel):
    status: str
    last_synced_at: Optional[str] = None
    node_count: int
    edge_count: int
