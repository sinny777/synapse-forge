from fastapi import HTTPException, Depends
from api.auth import get_current_user
from db.engine import AsyncSessionDep
from db.models import Workspace
import uuid

async def require_workspace_access(
    workspace_id: uuid.UUID,
    session: AsyncSessionDep,
    user: dict = Depends(get_current_user),
    require_write: bool = False
) -> Workspace:
    ws = await session.get(Workspace, workspace_id)
    if ws is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
        
    email = user.get("email")
    if require_write:
        if email != "system" and ws.name in ("Default", "Default Workspace"):
            raise HTTPException(status_code=403, detail="Modifications to Default workspace are forbidden")
            
        if email != "system" and ws.created_by and ws.created_by != email:
            shared_with = ws.shared_with or []
            if email not in shared_with:
                raise HTTPException(status_code=403, detail="Not authorized to modify this workspace")
                
    return ws
