from fastapi import HTTPException, status
from typing import Any, Dict, Optional

class BaseAPIException(HTTPException):
    """Р‘Р°Р·РѕРІРѕРµ РёСЃРєР»СЋС‡РµРЅРёРµ API."""
    
    def __init__(
        self, 
        status_code: int,
        detail: Any = None,
        headers: Optional[Dict[str, Any]] = None
    ):
        super().__init__(status_code=status_code, detail=detail, headers=headers)

class ValidationError(BaseAPIException):
    """РћС€РёР±РєР° РІР°Р»РёРґР°С†РёРё РґР°РЅРЅС‹С…."""
    
    def __init__(self, detail: str = "Validation error"):
        super().__init__(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=detail
        )

class NotFoundError(BaseAPIException):
    """Р РµСЃСѓСЂСЃ РЅРµ РЅР°Р№РґРµРЅ."""
    
    def __init__(self, detail: str = "Not found"):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=detail
        )

class UnauthorizedError(BaseAPIException):
    """РћС€РёР±РєР° Р°РІС‚РѕСЂРёР·Р°С†РёРё."""
    
    def __init__(self, detail: str = "Unauthorized"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail
        )

class ForbiddenError(BaseAPIException):
    """Р”РѕСЃС‚СѓРї Р·Р°РїСЂРµС‰РµРЅ."""
    
    def __init__(self, detail: str = "Forbidden"):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail
        )

class InternalServerError(BaseAPIException):
    """Р’РЅСѓС‚СЂРµРЅРЅСЏСЏ РѕС€РёР±РєР° СЃРµСЂРІРµСЂР°."""
    
    def __init__(self, detail: str = "Internal server error"):
        super().__init__(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=detail
        )
