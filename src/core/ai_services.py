from openai import OpenAI
from typing import Optional, BinaryIO
import json
import httpx
from io import BytesIO

from src.core.config import settings


class AIService:
    def __init__(self):
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)
        self.whisper_url = settings.WHISPER_SERVER_URL
        self.use_local_whisper = settings.USE_LOCAL_WHISPER

    async def transcribe_audio(self, audio_file: BinaryIO, filename: str = "audio.mp3") -> Optional[dict]:
        """Транскрибация аудио через Whisper (локальный сервер или OpenAI API)"""
        if self.use_local_whisper and self.whisper_url:
            return await self._transcribe_local_whisper(audio_file, filename)
        else:
            return await self._transcribe_openai_whisper(audio_file, filename)

    async def _transcribe_openai_whisper(self, audio_file: BinaryIO, filename: str = "audio.mp3") -> Optional[dict]:
        """Транскрибация через OpenAI Whisper API"""
        try:
            # Читаем аудио
            audio_file.seek(0)
            
            transcript = self.client.audio.transcriptions.create(
                model=settings.WHISPER_MODEL,
                file=(filename.replace('.mp3', '.wav'), audio_file),
                response_format="verbose_json",
                timestamp_granularities=["word", "segment"]
            )
            return transcript.model_dump()
        except Exception as e:
            print(f"Error transcribing audio with OpenAI: {e}")
            return None

    async def _transcribe_local_whisper(self, audio_file: BinaryIO, filename: str = "audio.mp3") -> Optional[dict]:
        """Транскрибация через локальный Whisper сервер"""
        try:
            # Читаем аудио файл
            audio_file.seek(0)
            audio_bytes = audio_file.read()
            
            # Отправляем на Whisper сервер
            async with httpx.AsyncClient(timeout=600) as client:
                files = {"file": (filename.replace('.mp3', '.wav'), audio_bytes)}
                response = await client.post(self.whisper_url, files=files)
                response.raise_for_status()
                
                result = response.json()
                
                # Преобразуем результат локального Whisper в формат, совместимый с OpenAI
                # Если результат уже в правильном формате (содержит 'text')
                if isinstance(result, dict) and "text" in result:
                    return result
                
                # Иначе, нужно преобразовать результат
                transcript_text = ""
                segments = []
                
                # Обработка списка сегментов
                items = []
                if isinstance(result, list):
                    items = result
                elif isinstance(result, dict):
                    items = result.get("segments", result.get("results", []))
                
                # Если items - это список, обрабатываем каждый элемент
                if isinstance(items, list):
                    for item in items:
                        if isinstance(item, dict):
                            start = item.get("start", 0)
                            end = item.get("end", 0)
                            text = item.get("text", "")
                            transcript_text += text + " "
                            segments.append({
                                "id": len(segments),
                                "seek": 0,
                                "start": float(start),
                                "end": float(end),
                                "text": text,
                                "tokens": [],
                                "temperature": 0.0,
                                "avg_logprob": 0.0,
                                "compression_ratio": 0.0,
                                "no_speech_prob": 0.0,
                                "words": [{"word": text, "start": float(start), "end": float(end)}]
                            })
                
                return {
                    "text": transcript_text.strip(),
                    "segments": segments,
                    "language": "ru"
                }
                    
        except Exception as e:
            print(f"Error transcribing audio with local Whisper: {e}")
            return None

    async def summarize_transcript(self, transcript_text: str, meeting_title: str = "") -> Optional[str]:
        """Суммаризация транскрипта через ChatGPT"""
        try:
            prompt = f"""Ты - ассистент для менеджеров проектов. Проанализируй транскрипт встречи и создай краткое резюме.

Название встречи: {meeting_title if meeting_title else "Без названия"}

Транскрипт:
{transcript_text}

Создай структурированное резюме встречи, включающее:
1. Основные темы обсуждения
2. Ключевые решения
3. Важные моменты и договоренности
4. Упомянутые проблемы или риски (если есть)

Ответ должен быть на русском языке, структурированным и кратким (не более 500 слов)."""

            response = self.client.chat.completions.create(
                model=settings.GPT_MODEL,
                messages=[
                    {"role": "system", "content": "Ты - профессиональный ассистент для менеджеров проектов. Твоя задача - создавать краткие и структурированные резюме встреч на русском языке."},
                    {"role": "user", "content": prompt}
                ],
                temperature=1,
                max_completion_tokens=1000
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"Error summarizing transcript: {e}")
            return None

    async def extract_action_items(self, transcript_text: str) -> Optional[list[dict]]:
        """Извлечение action items из транскрипта"""
        try:
            prompt = f"""Проанализируй транскрипт встречи и извлеки все задачи (action items) и договоренности.

Транскрипт:
{transcript_text}

Для каждой задачи определи:
- title: краткое название задачи
- description: подробное описание
- assignee: кто ответственен (если упоминается имя)

Верни результат ТОЛЬКО в формате JSON массива:
[
  {{"title": "...", "description": "...", "assignee": "..."}},
  ...
]

Если задач нет, верни пустой массив: []"""

            response = self.client.chat.completions.create(
                model=settings.GPT_MODEL,
                messages=[
                    {"role": "system", "content": "Ты - ассистент для извлечения задач из транскриптов встреч. Отвечай ТОЛЬКО валидным JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=1,
                max_completion_tokens=800,
                response_format={"type": "json_object"}
            )
            
            result = json.loads(response.choices[0].message.content)
            # ChatGPT может вернуть объект с ключом "action_items" или массив напрямую
            if isinstance(result, dict) and "action_items" in result:
                return result["action_items"]
            elif isinstance(result, list):
                return result
            else:
                return []
        except Exception as e:
            print(f"Error extracting action items: {e}")
            return []


ai_service = AIService()

