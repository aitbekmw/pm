# Telegram compare bot

Бот для сравнения транскрибации на одном и том же аудио:

- ElevenLabs Scribe v2 с включенной диаризацией.
- Текущий production Whisper endpoint из `WHISPER_SERVER_URL`.

Бот принимает голосовые сообщения Telegram, аудиофайлы и audio/video documents.
Файл держится только в памяти процесса и одинаковыми байтами отправляется в оба
backend'а транскрибации.

## Required env

Добавьте эти значения в `.env` на сервере:

```env
TELEGRAM_BOT_TOKEN=
ELEVENLABS_API_KEY=
WHISPER_SERVER_URL=http://10.0.10.3:8000/transcribe
```

Рекомендуемое ограничение доступа:

```env
TELEGRAM_ALLOWED_USER_IDS=123456789,987654321
```

Опциональные настройки ElevenLabs:

```env
ELEVENLABS_STT_MODEL=scribe_v2
ELEVENLABS_DIARIZE=true
ELEVENLABS_TAG_AUDIO_EVENTS=true
ELEVENLABS_TIMESTAMPS_GRANULARITY=word
ELEVENLABS_NUM_SPEAKERS=0
ELEVENLABS_KEYTERMS=Minvest,MDigital,PM Assistant
```

`ELEVENLABS_NUM_SPEAKERS=0` оставляет автоопределение количества спикеров.
Если количество известно заранее, можно поставить `2`, `3` и т.д.

## Run

```bash
docker compose -f docker-compose.telegram.yml up -d --build telegram-compare-bot
```

Проверить логи:

```bash
docker logs -f telegram-compare-bot
```

Остановить:

```bash
docker compose -f docker-compose.telegram.yml stop telegram-compare-bot
```
