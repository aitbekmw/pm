from openai import OpenAI
from typing import Optional, BinaryIO
import json

from src.core.config import settings


class AIService:
    def __init__(self):
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)

    async def transcribe_audio(self, audio_file: BinaryIO, filename: str = "audio.mp3") -> Optional[dict]:
        """Транскрибация аудио через Whisper API"""
        try:
            transcript = self.client.audio.transcriptions.create(
                model=settings.WHISPER_MODEL,
                file=(filename, audio_file),
                response_format="verbose_json",
                timestamp_granularities=["word", "segment"]
            )
            return transcript.model_dump()
        except Exception as e:
            print(f"Error transcribing audio: {e}")
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
                temperature=0.3,
                max_tokens=1000
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
                temperature=0.2,
                max_tokens=800,
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

