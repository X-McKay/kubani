"""Cluster integration tests for Kubani Nexus.

Tests that validate integration with cluster-deployed services including:
- vLLM (LLM inference)
- Temporal (workflow orchestration)
- Redis (pub/sub)
- PostgreSQL (database)
- Qdrant (vector store)
- Neo4j (graph store)

These tests require cluster access and are typically run in CI/CD or
before deployment to validate production readiness.
"""
