import uuid

from fastapi import Depends, HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase

from api.auth import get_current_user
from db.engine import get_db, normalize_mongo_document
from db.models import Workspace


async def require_workspace_access(
    workspace_id: uuid.UUID,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user: dict = Depends(get_current_user),
    require_write: bool = False,
) -> Workspace:
    document = await db.workspaces.find_one({"_id": str(workspace_id)})
    normalized = normalize_mongo_document(document)
    if normalized is None:
        raise HTTPException(status_code=404, detail="Workspace not found")

    ws = Workspace.model_validate(normalized)
    email = user.get("email")

    if require_write:
        if email != "system" and ws.name in ("Default", "Default Workspace"):
            raise HTTPException(
                status_code=403,
                detail="Modifications to Default workspace are forbidden",
            )

        if email != "system" and ws.created_by and ws.created_by != email:
            shared_with = ws.shared_with or []
            if email not in shared_with:
                raise HTTPException(
                    status_code=403,
                    detail="Not authorized to modify this workspace",
                )

    return ws
