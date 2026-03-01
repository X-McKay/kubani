"""Pipeline module for the News Digest syndicate.

This module implements the Context Injection pattern, which separates
the pipeline's business logic from its execution environment (Temporal
vs. local). The core idea:

    1. Define a ``PipelineContext`` protocol that abstracts all I/O
       *and* observability (status, logging, pause/resume).
    2. Write the pipeline logic once, against this protocol.
    3. Provide concrete context implementations for each environment:
       - ``TemporalContext``: wraps Temporal activities and workflow APIs.
       - ``LocalContext``: uses in-memory mocks for standalone testing.

This lets you run, test, and debug the full pipeline locally without
Temporal, while preserving all Temporal features in production.
"""

from .context import PipelineContext
from .ingest import run_ingest_pipeline, IngestResult

__all__ = [
    "PipelineContext",
    "run_ingest_pipeline",
    "IngestResult",
]
