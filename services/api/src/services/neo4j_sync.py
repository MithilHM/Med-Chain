import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from neo4j import AsyncGraphDatabase, AsyncDriver
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from src.config import settings
from src.models import (
    Patient, Disease, Diagnosis, Medication, Prescription,
    SideEffect, ObservedAdverseEvent, Cohort, CohortMembership
)

logger = logging.getLogger("medchain.graph")

_driver: Optional[AsyncDriver] = None

# Local fallback in-memory graph projection
_fallback_graph: Dict[str, Any] = {
    "nodes": {},
    "edges": {},
    "last_synced_at": None,
    "status": "INITIALIZED"
}

async def get_neo4j_driver() -> Optional[AsyncDriver]:
    global _driver
    if _driver is None:
        try:
            driver = AsyncGraphDatabase.driver(
                settings.NEO4J_URI,
                auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
            )
            # Verify connectivity
            async with driver.session() as session:
                await session.run("RETURN 1 AS test")
            _driver = driver
            logger.info("Connected to live Neo4j instance.")
        except Exception as e:
            logger.warning(f"Neo4j connection failed ({e}). Using local in-memory graph projection fallback.")
            _driver = None
    return _driver

class GraphSyncService:
    @staticmethod
    async def rebuild_graph(db: AsyncSession) -> Dict[str, Any]:
        """
        Extracts all relational entities and relationships from PostgreSQL
        and projects them into Neo4j (or the local fallback projection).
        """
        driver = await get_neo4j_driver()
        now_str = datetime.now(timezone.utc).isoformat()

        # Fetch clinical records from relational store
        diseases = (await db.execute(select(Disease))).scalars().all()
        medications = (await db.execute(select(Medication))).scalars().all()
        side_effects = (await db.execute(select(SideEffect))).scalars().all()
        patients = (await db.execute(select(Patient))).scalars().all()
        diagnoses = (await db.execute(select(Diagnosis))).scalars().all()
        prescriptions = (await db.execute(select(Prescription))).scalars().all()
        adverse_events = (await db.execute(select(ObservedAdverseEvent))).scalars().all()

        nodes_dict = {}
        edges_list = []

        # Populate Nodes
        for d in diseases:
            nodes_dict[f"disease_{d.id}"] = {
                "id": f"disease_{d.id}",
                "label": "Disease",
                "properties": {"code": d.code, "name": d.name}
            }
        for m in medications:
            nodes_dict[f"med_{m.id}"] = {
                "id": f"med_{m.id}",
                "label": "Medication",
                "properties": {"code": m.code, "name": m.name, "drug_class": m.drug_class}
            }
        for se in side_effects:
            nodes_dict[f"se_{se.id}"] = {
                "id": f"se_{se.id}",
                "label": "SideEffect",
                "properties": {"code": se.code, "name": se.name}
            }
        for p in patients:
            # Graph uses pseudonymous identifier to preserve privacy
            nodes_dict[f"patient_{p.id}"] = {
                "id": f"patient_{p.id}",
                "label": "Patient",
                "properties": {"display_code": p.display_code, "sex": p.sex}
            }

        # Edges: HAS_DIAGNOSIS
        for diag in diagnoses:
            # Find visit patient
            from src.models import Visit
            visit = (await db.execute(select(Visit).where(Visit.id == diag.visit_id))).scalar_one_or_none()
            if visit:
                edges_list.append({
                    "id": f"edge_diag_{diag.id}",
                    "source": f"patient_{visit.patient_id}",
                    "target": f"disease_{diag.disease_id}",
                    "type": "HAS_DIAGNOSIS",
                    "properties": {"severity": diag.severity}
                })

        # Edges: RECEIVED
        for pr in prescriptions:
            from src.models import Visit
            visit = (await db.execute(select(Visit).where(Visit.id == pr.visit_id))).scalar_one_or_none()
            if visit:
                edges_list.append({
                    "id": f"edge_presc_{pr.id}",
                    "source": f"patient_{visit.patient_id}",
                    "target": f"med_{pr.medication_id}",
                    "type": "RECEIVED",
                    "properties": {"dose": pr.dose_text}
                })

        # Edges: OBSERVED_WITH (Medication -> SideEffect)
        for ae in adverse_events:
            if ae.prescription_id:
                presc = (await db.execute(select(Prescription).where(Prescription.id == ae.prescription_id))).scalar_one_or_none()
                if presc:
                    edges_list.append({
                        "id": f"edge_ae_{ae.id}",
                        "source": f"med_{presc.medication_id}",
                        "target": f"se_{ae.side_effect_id}",
                        "type": "OBSERVED_WITH",
                        "properties": {"evidence_quality": ae.evidence_quality, "severity": ae.severity}
                    })

        # Calculate Disease Co-occurrence edges
        patient_diseases: Dict[str, set] = {}
        for diag in diagnoses:
            from src.models import Visit
            visit = (await db.execute(select(Visit).where(Visit.id == diag.visit_id))).scalar_one_or_none()
            if visit:
                patient_diseases.setdefault(visit.patient_id, set()).add(diag.disease_id)

        cooccur_counts: Dict[tuple, int] = {}
        for pt_id, d_set in patient_diseases.items():
            sorted_d = sorted(list(d_set))
            for i in range(len(sorted_d)):
                for j in range(i + 1, len(sorted_d)):
                    pair = (sorted_d[i], sorted_d[j])
                    cooccur_counts[pair] = cooccur_counts.get(pair, 0) + 1

        for (d1, d2), count in cooccur_counts.items():
            edges_list.append({
                "id": f"cooccur_{d1}_{d2}",
                "source": f"disease_{d1}",
                "target": f"disease_{d2}",
                "type": "CO_OCCURS_WITH",
                "properties": {"patient_count": count}
            })

        # Update fallback projection
        _fallback_graph["nodes"] = nodes_dict
        _fallback_graph["edges"] = edges_list
        _fallback_graph["last_synced_at"] = now_str
        _fallback_graph["status"] = "SYNCHRONIZED"

        # If live Neo4j driver is active, project to Neo4j
        if driver:
            try:
                async with driver.session() as session:
                    await session.run("MATCH (n) DETACH DELETE n")
                    # In a production script, UNWIND batches are used.
                    # Here we execute idempotent node creation.
                    for n in nodes_dict.values():
                        query = f"MERGE (n:{n['label']} {{id: $id}}) SET n += $props"
                        await session.run(query, id=n["id"], props=n["properties"])
                    for e in edges_list:
                        query = f"""
                        MATCH (s {{id: $source}}), (t {{id: $target}})
                        MERGE (s)-[r:{e['type']}]->(t)
                        SET r += $props
                        """
                        await session.run(query, source=e["source"], target=e["target"], props=e["properties"])
            except Exception as e:
                logger.warning(f"Neo4j live projection write failed ({e}); local projection remains consistent.")

        return {
            "status": "SYNCHRONIZED",
            "node_count": len(nodes_dict),
            "edge_count": len(edges_list),
            "last_synced_at": now_str,
            "mode": "live_neo4j" if driver else "fallback_graph_projection"
        }

    @staticmethod
    async def get_graph_data(filter_type: Optional[str] = None) -> Dict[str, Any]:
        """Returns nodes and edges filtered by relationship or view."""
        nodes = list(_fallback_graph["nodes"].values())
        edges = _fallback_graph["edges"]

        if filter_type == "disease_cooccurrence":
            filtered_edges = [e for e in edges if e["type"] == "CO_OCCURS_WITH"]
            node_ids = {e["source"] for e in filtered_edges} | {e["target"] for e in filtered_edges}
            filtered_nodes = [n for n in nodes if n["id"] in node_ids]
            return {"nodes": filtered_nodes, "edges": filtered_edges}
        
        elif filter_type == "drug_side_effects":
            filtered_edges = [e for e in edges if e["type"] in ("OBSERVED_WITH", "RECEIVED")]
            node_ids = {e["source"] for e in filtered_edges} | {e["target"] for e in filtered_edges}
            filtered_nodes = [n for n in nodes if n["id"] in node_ids]
            return {"nodes": filtered_nodes, "edges": filtered_edges}

        return {
            "nodes": nodes,
            "edges": edges,
            "disclaimer": "Associations represent synthetic observed co-occurrences, not proven pharmacological causation."
        }

    @staticmethod
    def get_status() -> Dict[str, Any]:
        return {
            "status": _fallback_graph["status"],
            "last_synced_at": _fallback_graph["last_synced_at"],
            "node_count": len(_fallback_graph["nodes"]),
            "edge_count": len(_fallback_graph["edges"]),
            "mode": "live_neo4j" if _driver else "fallback_graph_projection"
        }
