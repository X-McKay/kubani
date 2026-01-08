"""
Chaos Engineering Tests for Kubani.

This module provides chaos testing capabilities using chaos-mesh to validate
system resilience under failure conditions.

Test Categories:
- Event Bus failures (Redis)
- Skill Library failures (Qdrant)
- Network partitions
- Resource exhaustion (CPU/Memory)
- LLM API failures
- Kubernetes API failures
- Cascading failures

Prerequisites:
- Chaos Mesh installed in the cluster
- Test cluster with agents deployed
- kubectl access configured

Usage:
    pytest tests/chaos/ -v --chaos
"""
