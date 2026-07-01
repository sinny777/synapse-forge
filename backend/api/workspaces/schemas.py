"""
api.workspaces.schemas
~~~~~~~~~~~~~~~~~~~~~~
Pydantic request/response models for workspace cloning and environment operations.
"""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CloneBatchRequest(BaseModel):
    """Request body for batch-cloning resources."""
    source_workspace_id: uuid.UUID | None = Field(
        default=None,
        description="Source workspace to clone from. If omitted, uses the Default Workspace.",
    )
    destination_workspace_id: uuid.UUID = Field(
        ...,
        description="Target workspace to clone resources into.",
    )
    resource_ids: list[uuid.UUID] = Field(
        ...,
        min_length=1,
        description="List of resource IDs to clone.",
    )


class CloneSingleRequest(BaseModel):
    """Request body for single-resource cloning."""
    destination_workspace_id: uuid.UUID = Field(
        ...,
        description="Target workspace to clone the resource into.",
    )


class CloneResult(BaseModel):
    """Response for a clone operation."""
    cloned: int = Field(..., description="Number of resources successfully cloned")
    skipped: int = Field(default=0, description="Number skipped (already exist)")
    errors: list[str] = Field(default_factory=list, description="Error messages for failed items")


class CloneWorkflowResourcesRequest(BaseModel):
    """Request body for cloning all workflow-required resources for a given phase."""
    destination_workspace_id: uuid.UUID
    phase: Literal["generate", "train", "run"]


class EnvironmentActionResponse(BaseModel):
    """Response returned by start/stop environment endpoints."""
    model_config = ConfigDict(from_attributes=True)

    workspace_id: uuid.UUID
    status: str
    message: str
    container_info: dict | None = None
