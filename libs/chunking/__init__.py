"""Local copy of the HCCP-Agents referral markdown chunker.

Atlas trace:
  DO: DO-58BD2EA0
  DI: DI-ACA9659D
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-58BD2EA0")

Used by validation scripts to chunk converted referral documents
without writing back to production Neo4j.
"""

from libs.chunking.referral_document_prep import (
    build_leo_chunk_records,
    chunk_markdown_text,
    make_chunk_id,
)

__all__ = [
    "build_leo_chunk_records",
    "chunk_markdown_text",
    "make_chunk_id",
]
