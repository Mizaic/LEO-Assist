"""
Phase 5: Load dm+d drug extension into Neo4j as (:DrugConcept) nodes.

Sources (XML):
  - f_vtm*.xml  → VTM  (Virtual Therapeutic Moiety)
  - f_vmp*.xml  → VMP  (Virtual Medicinal Product)
  - f_amp*.xml  → AMP  (Actual Medicinal Product)
  - f_vmpp*.xml → VMPP (Virtual Medicinal Product Pack)
  - f_ampp*.xml → AMPP (Actual Medicinal Product Pack)

Hierarchy: VTM ← VMP ← AMP, VMP ← VMPP ← AMPP
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from pathlib import Path

from neo4j import AsyncDriver

from .base import BatchWriter

logger = logging.getLogger(__name__)

MERGE_DRUG = """
UNWIND $rows AS r
MERGE (d:DrugConcept {id: r.id})
SET d.name = r.name,
    d.type = r.drug_type
"""

MERGE_DRUG_PARENT = """
UNWIND $rows AS r
MERGE (child:DrugConcept {id: r.child_id})
SET child.name = r.child_name, child.type = r.child_type
WITH child, r
MATCH (parent:DrugConcept {id: r.parent_id})
MERGE (child)-[:IS_A]->(parent)
"""

LINK_DRUG_TO_SNOMED = """
UNWIND $rows AS r
MATCH (d:DrugConcept {id: r.id})
MERGE (c:Concept {id: r.id})
MERGE (d)-[:SAME_AS]->(c)
"""


def _find_xml(base: Path, prefix: str) -> Path | None:
    matches = sorted(base.glob(f"{prefix}[0-9]*.xml"))
    return matches[-1] if matches else None


def _iter_vtm(filepath: Path):
    tree = ET.parse(filepath)
    for vtm in tree.getroot().iter("VTM"):
        vtm_id = vtm.findtext("VTMID")
        nm = vtm.findtext("NM")
        if vtm_id and nm:
            yield {"id": vtm_id, "name": nm, "drug_type": "VTM"}


def _iter_vmp(filepath: Path):
    tree = ET.parse(filepath)
    for vmps in tree.getroot().iter("VMPS"):
        for vmp in vmps.iter("VMP"):
            vpid = vmp.findtext("VPID")
            vtmid = vmp.findtext("VTMID")
            nm = vmp.findtext("NM")
            if vpid and nm:
                yield {
                    "child_id": vpid,
                    "child_name": nm,
                    "child_type": "VMP",
                    "parent_id": vtmid,
                }


def _iter_amp(filepath: Path):
    tree = ET.parse(filepath)
    for amps in tree.getroot().iter("AMPS"):
        for amp in amps.iter("AMP"):
            apid = amp.findtext("APID")
            vpid = amp.findtext("VPID")
            nm = amp.findtext("NM")
            if apid and nm:
                yield {
                    "child_id": apid,
                    "child_name": nm,
                    "child_type": "AMP",
                    "parent_id": vpid,
                }


def _iter_vmpp(filepath: Path):
    tree = ET.parse(filepath)
    for vmpps in tree.getroot().iter("VMPPS"):
        for vmpp in vmpps.iter("VMPP"):
            vppid = vmpp.findtext("VPPID")
            vpid = vmpp.findtext("VPID")
            nm = vmpp.findtext("NM")
            if vppid and nm:
                yield {
                    "child_id": vppid,
                    "child_name": nm,
                    "child_type": "VMPP",
                    "parent_id": vpid,
                }


def _iter_ampp(filepath: Path):
    tree = ET.parse(filepath)
    for ampps in tree.getroot().iter("AMPPS"):
        for ampp in ampps.iter("AMPP"):
            appid = ampp.findtext("APPID")
            apid = ampp.findtext("APID")
            nm = ampp.findtext("NM")
            if appid and nm:
                yield {
                    "child_id": appid,
                    "child_name": nm,
                    "child_type": "AMPP",
                    "parent_id": apid,
                }


async def load_dmd(
    driver: AsyncDriver,
    dmd_dir: Path,
    batch_size: int = 5_000,
) -> int:
    """Load all dm+d XML files into Neo4j."""
    total = 0

    vtm_file = _find_xml(dmd_dir, "f_vtm")
    if vtm_file:
        logger.info("Loading VTM from %s", vtm_file.name)
        async with driver.session() as session:
            writer = BatchWriter(session, MERGE_DRUG, batch_size, "VTM")
            for item in _iter_vtm(vtm_file):
                await writer.add(item)
            total += await writer.finish()

    child_loaders = [
        ("f_vmp", _iter_vmp, "VMP"),
        ("f_amp", _iter_amp, "AMP"),
        ("f_vmpp", _iter_vmpp, "VMPP"),
        ("f_ampp", _iter_ampp, "AMPP"),
    ]
    for prefix, iterator, label in child_loaders:
        xml_file = _find_xml(dmd_dir, prefix)
        if not xml_file:
            logger.warning("%s: no XML file found", label)
            continue
        logger.info("Loading %s from %s", label, xml_file.name)
        async with driver.session() as session:
            parent_writer = BatchWriter(
                session, MERGE_DRUG_PARENT, batch_size, label
            )
            orphan_writer = BatchWriter(
                session, MERGE_DRUG, batch_size, f"{label}/orphan"
            )
            for item in iterator(xml_file):
                if item["parent_id"]:
                    await parent_writer.add(item)
                else:
                    await orphan_writer.add({
                        "id": item["child_id"],
                        "name": item["child_name"],
                        "drug_type": item["child_type"],
                    })
            total += await parent_writer.finish()
            total += await orphan_writer.finish()

    logger.info("Linking DrugConcepts to existing SNOMED Concepts")
    async with driver.session() as session:
        writer = BatchWriter(
            session, LINK_DRUG_TO_SNOMED, batch_size, "Drug→SNOMED"
        )
        result = await session.run(
            "MATCH (d:DrugConcept) RETURN d.id AS id"
        )
        records = await result.data()
        for rec in records:
            await writer.add({"id": rec["id"]})
        total += await writer.finish()

    return total
