from __future__ import annotations

from fastapi import HTTPException, status


class ForbiddenRoleError(HTTPException):
    def __init__(self) -> None:
        super().__init__(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role permissions.")
