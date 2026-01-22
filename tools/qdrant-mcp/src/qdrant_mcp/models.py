"""
Qdrant MCP Server data models.

Pydantic models for vector search operations.
"""

from typing import Any

from pydantic import BaseModel, Field


class CollectionInfo(BaseModel):
    """Information about a Qdrant collection."""

    name: str = Field(description="Collection name")
    vectors_count: int = Field(description="Number of vectors in collection")
    points_count: int = Field(description="Number of points in collection")
    status: str = Field(description="Collection status")


class CollectionsResult(BaseModel):
    """Result model for listing collections."""

    collections: list[CollectionInfo] = Field(description="List of collections")
    count: int = Field(description="Number of collections")


class SearchResult(BaseModel):
    """A single search result."""

    id: str = Field(description="Point ID")
    score: float = Field(description="Similarity score")
    payload: dict[str, Any] = Field(default_factory=dict, description="Point metadata")


class SearchResults(BaseModel):
    """Result model for vector search."""

    results: list[SearchResult] = Field(description="Search results")
    count: int = Field(description="Number of results")


class PointResult(BaseModel):
    """Result model for a single point."""

    id: str = Field(description="Point ID")
    vector: list[float] = Field(description="Embedding vector")
    payload: dict[str, Any] = Field(default_factory=dict, description="Point metadata")


class UpsertResult(BaseModel):
    """Result model for upsert operation."""

    collection: str = Field(description="Collection name")
    upserted_count: int = Field(description="Number of points upserted")
    ids: list[str] = Field(description="IDs of upserted points")
