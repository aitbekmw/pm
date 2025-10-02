# Р”РµРїР»РѕР№

## РўСЂРµР±РѕРІР°РЅРёСЏ

- Docker
- Docker Compose
- GitLab CI/CD

## РџРµСЂРµРјРµРЅРЅС‹Рµ РѕРєСЂСѓР¶РµРЅРёСЏ

РЎРѕР·РґР°Р№С‚Рµ С„Р°Р№Р» `.env` СЃРѕ СЃР»РµРґСѓСЋС‰РёРјРё РїРµСЂРµРјРµРЅРЅС‹РјРё:

```
DATABASE_URL=postgresql+asyncpg://user:password@postgres:5432/dbname
POSTGRES_USER=user
POSTGRES_PASSWORD=password
POSTGRES_DB=dbname
RAG_OPENWEBUI_PORT=8002
```

## РџСЂРѕС†РµСЃСЃ РґРµРїР»РѕСЏ

1. Push РІ РІРµС‚РєСѓ `dev` Р·Р°РїСѓСЃРєР°РµС‚ Р°РІС‚РѕРјР°С‚РёС‡РµСЃРєРёР№ РґРµРїР»РѕР№
2. РћР±СЂР°Р· СЃРѕР±РёСЂР°РµС‚СЃСЏ Рё РїСѓС€РёС‚СЃСЏ РІ GitLab Registry
3. РќР° СЃРµСЂРІРµСЂРµ РІС‹РїРѕР»РЅСЏРµС‚СЃСЏ `docker compose up -d`
