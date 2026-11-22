"""Derived graph projection (Neo4j, with an in-memory development fallback).

The relational database is authoritative; this projection is rebuildable at any time.

Atomic rebuild: every rebuild writes a complete new generation (nodes and relationships tagged
with `generation`) next to the live one. Only after the whole write succeeds does a single
transaction point `(:ProjectionMeta {name:'current'})` at the new generation and delete older
generations. Readers always filter by the current generation, so a failed or half-finished
rebuild is never visible and the previous projection stays live.

Privacy: patient nodes carry a keyed pseudonym and sex only, never MRNs or names.
"""
import hashlib
import hmac
import logging
import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from neo4j import AsyncDriver, AsyncGraphDatabase
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.models import Diagnosis, Disease, Medication, ObservedAdverseEvent, Patient, Prescription, SideEffect, Visit

logger = logging.getLogger("medchain.graph")

_driver: Optional[AsyncDriver] = None
_last_connect_attempt = 0.0
_RECONNECT_BACKOFF_SECONDS = 30.0
_live_graph_status = "UNSYNCHRONIZED"
_live_graph_error: Optional[str] = None
_live_generation: Optional[str] = None
_last_ping: Dict[str, Any] = {"at": 0.0, "ok": False}
_BATCH = 500

_fallback_graph: Dict[str, Any] = {"nodes": {}, "edges": [], "last_synced_at": None, "status": "INITIALIZED"}


def patient_pseudonym(patient_id: str) -> str:
    return hmac.new(settings.CHAIN_PSEUDONYM_KEY.encode("utf-8"), f"graph:{patient_id}".encode("utf-8"),
                    hashlib.sha256).hexdigest()[:16]


async def get_neo4j_driver() -> Optional[AsyncDriver]:
    """Connect lazily; after a failure, wait before retrying instead of stalling every request."""
    global _driver, _last_connect_attempt
    if _driver is not None:
        return _driver
    if time.time() - _last_connect_attempt < _RECONNECT_BACKOFF_SECONDS:
        return None
    _last_connect_attempt = time.time()
    try:
        driver = AsyncGraphDatabase.driver(settings.NEO4J_URI, auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
                                           connection_timeout=3)
        await driver.verify_connectivity()
        _driver = driver
        logger.info("Connected to live Neo4j instance.")
    except Exception as exc:
        logger.warning("Neo4j unavailable (%s); using the in-memory projection.", exc)
        _driver = None
    return _driver


async def _build_projection(db: AsyncSession) -> Dict[str, Any]:
    diseases = (await db.execute(select(Disease))).scalars().all()
    medications = (await db.execute(select(Medication))).scalars().all()
    side_effects = (await db.execute(select(SideEffect))).scalars().all()
    patients = (await db.execute(select(Patient).where(Patient.record_status == "ACTIVE"))).scalars().all()
    active_ids = {p.id for p in patients}
    diagnosis_rows = (await db.execute(
        select(Diagnosis.id, Visit.patient_id, Diagnosis.disease_id, Diagnosis.severity)
        .join(Visit, Visit.id == Diagnosis.visit_id).where(Visit.status == "ACTIVE")
    )).all()
    prescription_rows = (await db.execute(
        select(Prescription.id, Visit.patient_id, Prescription.medication_id, Prescription.dose_text)
        .join(Visit, Visit.id == Prescription.visit_id).where(Visit.status == "ACTIVE")
    )).all()
    adverse_rows = (await db.execute(
        select(ObservedAdverseEvent.patient_id, Prescription.medication_id, ObservedAdverseEvent.side_effect_id,
               ObservedAdverseEvent.evidence_quality)
        .join(Prescription, Prescription.id == ObservedAdverseEvent.prescription_id)
    )).all()

    nodes: Dict[str, Dict[str, Any]] = {}
    for d in diseases:
        nodes[f"disease_{d.id}"] = {"id": f"disease_{d.id}", "label": "Disease", "properties": {"code": d.code, "name": d.name}}
    for m in medications:
        nodes[f"med_{m.id}"] = {"id": f"med_{m.id}", "label": "Medication",
                                "properties": {"code": m.code, "name": m.name, "drug_class": m.drug_class}}
    for se in side_effects:
        nodes[f"se_{se.id}"] = {"id": f"se_{se.id}", "label": "SideEffect", "properties": {"code": se.code, "name": se.name}}
    for p in patients:
        nodes[f"patient_{patient_pseudonym(p.id)}"] = {
            "id": f"patient_{patient_pseudonym(p.id)}", "label": "Patient",
            "properties": {"pseudonym": patient_pseudonym(p.id), "sex": p.sex},
        }

    def pnode(patient_id: str) -> str:
        return f"patient_{patient_pseudonym(patient_id)}"

    edges: List[Dict[str, Any]] = []
    patient_diseases: Dict[str, set] = defaultdict(set)
    for diagnosis_id, patient_id, disease_id, severity in diagnosis_rows:
        if patient_id not in active_ids:
            continue
        patient_diseases[patient_id].add(disease_id)
        edges.append({"id": f"diag_{diagnosis_id}", "source": pnode(patient_id), "target": f"disease_{disease_id}",
                      "type": "HAS_DIAGNOSIS", "properties": {"severity": severity}})
    for prescription_id, patient_id, medication_id, dose in prescription_rows:
        if patient_id in active_ids:
            edges.append({"id": f"rx_{prescription_id}", "source": pnode(patient_id), "target": f"med_{medication_id}",
                          "type": "RECEIVED", "properties": {"dose": dose}})

    # Patient-level adverse events keep the medication, so traversals count real patients.
    observed_patients: Dict[tuple, set] = defaultdict(set)
    evidence: Dict[tuple, str] = {}
    for patient_id, medication_id, side_effect_id, quality in adverse_rows:
        if patient_id not in active_ids:
            continue
        observed_patients[(medication_id, side_effect_id)].add(patient_id)
        evidence[(medication_id, side_effect_id)] = quality
        edges.append({"id": f"exp_{patient_pseudonym(patient_id)}_{medication_id}_{side_effect_id}",
                      "source": pnode(patient_id), "target": f"se_{side_effect_id}", "type": "EXPERIENCED",
                      "properties": {"medication_id": f"med_{medication_id}"}})
    for (medication_id, side_effect_id), patient_set in observed_patients.items():
        edges.append({"id": f"obs_{medication_id}_{side_effect_id}", "source": f"med_{medication_id}",
                      "target": f"se_{side_effect_id}", "type": "OBSERVED_WITH",
                      "properties": {"patient_count": len(patient_set), "evidence_quality": evidence[(medication_id, side_effect_id)]}})

    pair_counts: Dict[tuple, int] = defaultdict(int)
    for disease_set in patient_diseases.values():
        ordered = sorted(disease_set)
        for i in range(len(ordered)):
            for j in range(i + 1, len(ordered)):
                pair_counts[(ordered[i], ordered[j])] += 1
    for (d1, d2), count in pair_counts.items():
        edges.append({"id": f"cooccur_{d1}_{d2}", "source": f"disease_{d1}", "target": f"disease_{d2}",
                      "type": "CO_OCCURS_WITH", "properties": {"patient_count": count}})

    # Deduplicate edge ids (e.g. repeated adverse events for one patient/medication/effect).
    unique_edges = list({edge["id"]: edge for edge in edges}.values())
    return {"nodes": nodes, "edges": unique_edges}


async def _write_generation(driver: AsyncDriver, projection: Dict[str, Any], generation: str) -> None:
    nodes_by_label: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for node in projection["nodes"].values():
        nodes_by_label[node["label"]].append({"id": node["id"], "props": node["properties"]})
    label_of = {node["id"]: node["label"] for node in projection["nodes"].values()}
    edges_by_shape: Dict[tuple, List[Dict[str, Any]]] = defaultdict(list)
    for edge in projection["edges"]:
        shape = (edge["type"], label_of.get(edge["source"]), label_of.get(edge["target"]))
        if shape[1] and shape[2]:
            edges_by_shape[shape].append({"s": edge["source"], "t": edge["target"], "props": edge["properties"]})

    async with driver.session() as session:
        # Labels and relationship types come from code, never from input.
        for label in nodes_by_label:
            await session.run(
                f"CREATE INDEX medchain_{label.lower()}_gen IF NOT EXISTS FOR (n:{label}) ON (n.id, n.generation)"
            )
        for label, rows in nodes_by_label.items():
            for start in range(0, len(rows), _BATCH):
                await session.run(
                    f"UNWIND $rows AS row CREATE (n:{label} {{id: row.id, generation: $gen}}) SET n += row.props",
                    rows=rows[start:start + _BATCH], gen=generation,
                )
        for (rel_type, source_label, target_label), rows in edges_by_shape.items():
            for start in range(0, len(rows), _BATCH):
                await session.run(
                    "UNWIND $rows AS row "
                    f"MATCH (s:{source_label} {{id: row.s, generation: $gen}}), "
                    f"(t:{target_label} {{id: row.t, generation: $gen}}) "
                    f"CREATE (s)-[r:{rel_type}]->(t) SET r += row.props",
                    rows=rows[start:start + _BATCH], gen=generation,
                )

        async def swap(tx):
            await tx.run("MERGE (m:ProjectionMeta {name: 'current'}) SET m.generation = $gen, m.synced_at = $at",
                         gen=generation, at=datetime.now(timezone.utc).isoformat())
            await tx.run("MATCH (n) WHERE n.generation IS NOT NULL AND n.generation <> $gen DETACH DELETE n", gen=generation)

        await session.execute_write(swap)


async def _discard_generation(driver: AsyncDriver, generation: str) -> None:
    try:
        async with driver.session() as session:
            await session.run("MATCH (n {generation: $gen}) DETACH DELETE n", gen=generation)
    except Exception as exc:
        logger.warning("Could not clean up failed graph generation %s: %s", generation, exc)


class GraphSyncService:
    @staticmethod
    async def rebuild_graph(db: AsyncSession) -> Dict[str, Any]:
        global _live_graph_status, _live_graph_error, _live_generation
        driver = await get_neo4j_driver()
        now_str = datetime.now(timezone.utc).isoformat()
        projection = await _build_projection(db)

        _fallback_graph.update(nodes=projection["nodes"], edges=projection["edges"],
                               last_synced_at=now_str, status="SYNCHRONIZED")

        if driver:
            generation = uuid.uuid4().hex
            _live_graph_status, _live_graph_error = "SYNCING", None
            try:
                await _write_generation(driver, projection, generation)
                _live_generation = generation
                _live_graph_status, _live_graph_error = "SYNCHRONIZED", None
            except Exception as exc:
                await _discard_generation(driver, generation)
                _live_graph_status, _live_graph_error = "SYNC_FAILED", str(exc)[:300]
                logger.warning("Neo4j rebuild failed; the previous generation stays live: %s", exc)

        return {
            "status": _live_graph_status if driver else _fallback_graph["status"],
            "node_count": len(projection["nodes"]),
            "edge_count": len(projection["edges"]),
            "last_synced_at": now_str,
            "mode": "live_neo4j" if driver else "fallback_graph_projection",
            "generation": _live_generation if driver else None,
            "error": _live_graph_error if driver else None,
        }

    @staticmethod
    async def get_graph_data(filter_type: Optional[str] = None) -> Dict[str, Any]:
        """Admin view of the projection (patients appear only as pseudonyms)."""
        nodes = list(_fallback_graph["nodes"].values())
        edges = _fallback_graph["edges"]
        if filter_type == "disease_cooccurrence":
            edges = [e for e in edges if e["type"] == "CO_OCCURS_WITH"]
        elif filter_type == "drug_side_effects":
            edges = [e for e in edges if e["type"] in ("OBSERVED_WITH", "RECEIVED")]
        if filter_type:
            node_ids = {e["source"] for e in edges} | {e["target"] for e in edges}
            nodes = [n for n in nodes if n["id"] in node_ids]
        return {
            "nodes": nodes,
            "edges": edges,
            "disclaimer": "Associations are observed co-occurrences in recorded data, not proven pharmacological causation.",
        }

    @staticmethod
    def get_status() -> Dict[str, Any]:
        is_live = _driver is not None
        status = _live_graph_status if is_live else _fallback_graph["status"]
        synced = _fallback_graph["last_synced_at"]
        if status == "SYNCHRONIZED" and synced:
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(synced)).total_seconds()
            if age > settings.GRAPH_STALE_AFTER_SECONDS:
                status = "STALE"
        if is_live and _last_ping["at"] and not _last_ping["ok"]:
            status = "UNREACHABLE"
        return {
            "status": status,
            "last_synced_at": synced,
            "node_count": len(_fallback_graph["nodes"]),
            "edge_count": len(_fallback_graph["edges"]),
            "mode": "live_neo4j" if is_live else "fallback_graph_projection",
            "generation": _live_generation if is_live else None,
            "error": _live_graph_error if is_live else None,
        }

    @staticmethod
    async def get_status_async() -> Dict[str, Any]:
        """Status with a live connectivity check (cached for 30 seconds)."""
        if _driver is not None and time.time() - _last_ping["at"] > 30:
            try:
                await _driver.verify_connectivity()
                _last_ping.update(at=time.time(), ok=True)
            except Exception:
                _last_ping.update(at=time.time(), ok=False)
        return GraphSyncService.get_status()

    @staticmethod
    async def find_side_effect_profiles(disease_code: str = "E11") -> list:
        """Distinct patients with the disease who received a medication and then experienced a side effect on it.

        (:Patient)-[:HAS_DIAGNOSIS]->(:Disease), (:Patient)-[:RECEIVED]->(:Medication),
        (:Patient)-[:EXPERIENCED {medication_id}]->(:SideEffect). Returns [] when nothing matches;
        results are never invented.
        """
        driver = await get_neo4j_driver()
        if driver and _live_generation:
            try:
                async with driver.session() as session:
                    result = await session.run(
                        "MATCH (meta:ProjectionMeta {name: 'current'}) "
                        "MATCH (d:Disease {code: $code, generation: meta.generation})<-[:HAS_DIAGNOSIS]-(p:Patient)"
                        "-[:RECEIVED]->(m:Medication), (p)-[x:EXPERIENCED]->(s:SideEffect) "
                        "WHERE x.medication_id = m.id "
                        "RETURN m.name AS medication, s.name AS side_effect, count(DISTINCT p) AS patient_count "
                        "ORDER BY patient_count DESC",
                        code=disease_code,
                    )
                    return await result.data()
            except Exception as exc:
                logger.warning("Neo4j path query failed, using the in-memory projection: %s", exc)

        nodes, edges = _fallback_graph["nodes"], _fallback_graph["edges"]
        disease_ids = {nid for nid, n in nodes.items() if n["label"] == "Disease" and n["properties"].get("code") == disease_code}
        diagnosed = {e["source"] for e in edges if e["type"] == "HAS_DIAGNOSIS" and e["target"] in disease_ids}
        received = defaultdict(set)
        for e in edges:
            if e["type"] == "RECEIVED" and e["source"] in diagnosed:
                received[e["source"]].add(e["target"])
        counts: Dict[tuple, set] = defaultdict(set)
        for e in edges:
            if e["type"] == "EXPERIENCED" and e["source"] in diagnosed:
                medication = e["properties"].get("medication_id")
                if medication in received[e["source"]]:
                    counts[(medication, e["target"])].add(e["source"])
        profiles = [
            {"medication": nodes[m]["properties"]["name"], "side_effect": nodes[s]["properties"]["name"],
             "patient_count": len(patient_set)}
            for (m, s), patient_set in counts.items() if m in nodes and s in nodes
        ]
        return sorted(profiles, key=lambda item: -item["patient_count"])
