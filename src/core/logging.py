import logging
import sys
from typing import Dict, Any

def setup_logging(level: str = "INFO") -> None:
    """РќР°СЃС‚СЂРѕР№РєР° Р»РѕРіРёСЂРѕРІР°РЅРёСЏ РґР»СЏ РїСЂРёР»РѕР¶РµРЅРёСЏ."""
    
    # РќР°СЃС‚СЂРѕР№РєР° С„РѕСЂРјР°С‚Р°
    formatter = logging.Formatter(
        fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    # РќР°СЃС‚СЂРѕР№РєР° handler РґР»СЏ stdout
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    
    # РќР°СЃС‚СЂРѕР№РєР° root logger
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        handlers=[handler],
        force=True
    )
    
    # РќР°СЃС‚СЂРѕР№РєР° Р»РѕРіРіРµСЂРѕРІ СЃС‚РѕСЂРѕРЅРЅРёС… Р±РёР±Р»РёРѕС‚РµРє
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

def get_logger(name: str) -> logging.Logger:
    """РџРѕР»СѓС‡РµРЅРёРµ Р»РѕРіРіРµСЂР° СЃ РЅР°СЃС‚СЂРѕРµРЅРЅС‹Рј РёРјРµРЅРµРј."""
    return logging.getLogger(name)
