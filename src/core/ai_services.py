# Старый код OpenAI (закомментирован)
# from openai import OpenAI
from google import generativeai as genai
from typing import Optional, BinaryIO
import json
import re
import httpx
import logging
import tempfile
import os
from src.core.config import settings

logger = logging.getLogger(__name__)


class TranscriptionError(Exception):
    """Ошибка транскрибации с описанием причины"""
    def __init__(self, message: str, reason: str = "unknown"):
        self.reason = reason
        super().__init__(message)


class AIService:
    def __init__(self):
        # Старый код OpenAI (закомментирован)
        # self.client = OpenAI(api_key=settings.OPENAI_API_KEY)
        
        # Новая реализация Gemini
        genai.configure(api_key=settings.GEMINI_API_KEY)
        self.model = genai.GenerativeModel(settings.GEMINI_MODEL)
        
        self.whisper_url = settings.WHISPER_SERVER_URL
        self.use_local_whisper = settings.USE_LOCAL_WHISPER

    async def transcribe_audio(self, audio_file: BinaryIO, filename: str = "audio.wav") -> Optional[dict]:
        """Транскрибация WAV аудио через Whisper"""
        if self.use_local_whisper and self.whisper_url:
            return await self._transcribe_local_whisper(audio_file, filename)
        else:
            # Используем локальный Whisper по умолчанию, так как Gemini не имеет прямого API для транскрибации
            return await self._transcribe_local_whisper(audio_file, filename)
            # Старый код OpenAI Whisper (закомментирован)
            # return await self._transcribe_openai_whisper(audio_file, filename)

    # Старый код OpenAI Whisper (закомментирован)
    # async def _transcribe_openai_whisper(self, audio_file: BinaryIO, filename: str = "audio.wav") -> Optional[dict]:
    #     """Транскрибация через OpenAI Whisper API"""
    #     try:
    #         audio_file.seek(0)
    #         audio_bytes = audio_file.read()

    #         with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp_file:
    #             wav_path = tmp_file.name
    #             tmp_file.write(audio_bytes)

    #         try:
    #             with open(wav_path, 'rb') as wav_file:
    #                 transcript = self.client.audio.transcriptions.create(
    #                     model=settings.WHISPER_MODEL,
    #                     file=(filename, wav_file),
    #                     response_format="verbose_json",
    #                     timestamp_granularities=["word", "segment"]
    #                 )

    #             return transcript.model_dump()

    #         finally:
    #             if os.path.exists(wav_path):
    #                 os.unlink(wav_path)

    #     except Exception as e:
    #         logger.error(f"Error transcribing audio with OpenAI: {e}", exc_info=True)
    #         return None

    async def _transcribe_local_whisper(self, audio_file: BinaryIO, filename: str = "audio.wav") -> Optional[dict]:
        """Транскрибация через локальный Whisper сервер.
        
        Raises:
            TranscriptionError: При ошибке транскрибации с описанием причины.
        """
        tmp_wav_path = None
        try:
            audio_file.seek(0)
            audio_bytes = audio_file.read()

            if not audio_bytes or len(audio_bytes) < 100:
                raise TranscriptionError(
                    "Аудиофайл пуст или повреждён. Загрузите корректный файл.",
                    reason="empty_audio_file"
                )

            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp_file:
                tmp_wav_path = tmp_file.name
                tmp_file.write(audio_bytes)

            try:
                with open(tmp_wav_path, 'rb') as wav_file:
                    wav_bytes = wav_file.read()

                try:
                    async with httpx.AsyncClient(timeout=600) as client:
                        files = {"file": (filename, wav_bytes)}
                        response = await client.post(self.whisper_url, files=files)
                        response.raise_for_status()
                except httpx.ConnectError:
                    raise TranscriptionError(
                        "Сервер транскрибации недоступен. Попробуйте позже.",
                        reason="whisper_unavailable"
                    )
                except httpx.TimeoutException:
                    raise TranscriptionError(
                        "Превышено время ожидания ответа от сервера транскрибации. Попробуйте позже или загрузите файл меньшего размера.",
                        reason="whisper_timeout"
                    )
                except httpx.HTTPStatusError as http_err:
                    raise TranscriptionError(
                        f"Сервер транскрибации вернул ошибку (HTTP {http_err.response.status_code}). Попробуйте позже.",
                        reason="whisper_http_error"
                    )

                result = response.json()
                
                # Логируем сырой ответ от Whisper для диагностики
                logger.info(f"Whisper raw response (first 500 chars): {str(result)[:500]}")

                # Тексты-заглушки которые Whisper может вернуть вместо реальной транскрибации
                WHISPER_EMPTY_PLACEHOLDERS = {
                    "text is empty",
                    "no speech detected",
                    "audio is too short",
                    "no text",
                    "",
                }

                def _is_empty_transcript(text: str) -> bool:
                    """Проверяет, является ли текст пустым или заглушкой от Whisper"""
                    if not text:
                        return True
                    return text.strip().lower() in WHISPER_EMPTY_PLACEHOLDERS

                if isinstance(result, dict) and "text" in result:
                    text = result.get("text", "").strip()
                    if _is_empty_transcript(text):
                        whisper_msg = f" (Whisper вернул: \"{text}\")" if text else ""
                        raise TranscriptionError(
                            f"В аудиозаписи не обнаружена речь.{whisper_msg} Убедитесь, что файл содержит голосовые данные.",
                            reason="no_speech_detected"
                        )
                    return result

                transcript_text = ""
                segments = []

                items = result if isinstance(result, list) else result.get("segments", [])

                if not items:
                    raise TranscriptionError(
                        "Звук неразборчив или отсутствует, попробуйте загрузить запись с более четким звуком",
                        reason="no_speech_detected"
                    )

                for idx, item in enumerate(items):
                    if isinstance(item, dict):
                        start = float(item.get("start", 0))
                        end = float(item.get("end", 0))
                        text = item.get("text", "")
                        transcript_text += text + " "
                        segments.append({
                            "id": idx,
                            "seek": 0,
                            "start": start,
                            "end": end,
                            "text": text,
                            "tokens": [],
                            "temperature": 0.0,
                            "avg_logprob": 0.0,
                            "compression_ratio": 0.0,
                            "no_speech_prob": 0.0,
                        })

                final_text = transcript_text.strip()
                if _is_empty_transcript(final_text):
                    whisper_msg = f" (Whisper вернул: \"{final_text}\")" if final_text else ""
                    raise TranscriptionError(
                        f"В аудиозаписи не обнаружена речь.{whisper_msg} Убедитесь, что файл содержит голосовые данные.",
                        reason="no_speech_detected"
                    )

                return {
                    "text": final_text,
                    "segments": segments,
                    "language": "ru"
                }

            finally:
                if tmp_wav_path and os.path.exists(tmp_wav_path):
                    os.unlink(tmp_wav_path)

        except TranscriptionError:
            raise  # Пробрасываем наши ошибки без изменений
        except Exception as e:
            logger.error(f"Error transcribing audio with local Whisper: {e}", exc_info=True)
            raise TranscriptionError(
                f"Непредвиденная ошибка транскрибации: {str(e)}",
                reason="unexpected_error"
            )

    async def summarize_transcript(self, transcript_text: str, meeting_title: str = "") -> Optional[str]:
        """Суммаризация транскрипта"""
        try:
            if not transcript_text or not transcript_text.strip():
                logger.warning("transcript_text is empty")
                return "Нет текста для суммаризации"

            prompt = f"""Проанализируй транскрипт встречи и создай краткое резюме.
Название встречи: {meeting_title if meeting_title else "Без названия"}
Транскрипт:
{transcript_text}
Создай структурированное резюме, включающее:
1. Основные темы обсуждения
2. Ключевые решения
3. Важные моменты и договоренности
4. Упомянутые проблемы или риски

Ответ на русском языке, структурированный (максимум 500 слов)."""

            # Старый код OpenAI (закомментирован)
            # response = self.client.chat.completions.create(
            #     model=settings.GPT_MODEL,
            #     messages=[
            #         {"role": "system", "content": "Ты - профессиональный ассистент для менеджеров проектов. Создавай краткие структурированные резюме встреч на русском языке."},
            #         {"role": "user", "content": prompt}
            #     ],
            #     temperature=1,
            #     max_completion_tokens=1000
            # )
            # result = response.choices[0].message.content

            # Новая реализация Gemini
            system_instruction = "Ты - профессиональный ассистент для менеджеров проектов. Создавай краткие структурированные резюме встреч на русском языке."
            
            # Создаем модель с system instruction для этого запроса
            model_with_instruction = genai.GenerativeModel(
                model_name=settings.GEMINI_MODEL,
                system_instruction=system_instruction
            )
            
            response = model_with_instruction.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=1.0,
                    max_output_tokens=2500,
                )
            )

            result = response.text
            logger.info(f"Summarization completed successfully, result length: {len(result) if result else 0}")
            return result

        except Exception as e:
            logger.error(f"Error summarizing transcript: {e}", exc_info=True)
            return None

    async def extract_action_items(self, transcript_text: str) -> Optional[list[dict]]:
        """Извлечение action items из транскрипта"""
        try:
            if not transcript_text or not transcript_text.strip():
                logger.warning("transcript_text is empty for action items extraction")
                return []

            prompt = f"""Проанализируй транскрипт встречи и извлеки все задачи (action items).
Транскрипт:
{transcript_text}
Для каждой задачи определи:
- title: краткое название
- description: описание
- assignee: ответственный (если упоминается)

Верни ТОЛЬКО JSON массив:
[
  {{"title": "...", "description": "...", "assignee": "..."}},
  ...
]
Если задач нет, верни: []"""

            # Старый код OpenAI (закомментирован)
            # response = self.client.chat.completions.create(
            #     model=settings.GPT_MODEL,
            #     messages=[
            #         {"role": "system", "content": "Ты - ассистент для извлечения задач из транскриптов. Отвечай ТОЛЬКО валидным JSON."},
            #         {"role": "user", "content": prompt}
            #     ],
            #     temperature=1,
            #     max_completion_tokens=800,
            #     response_format={"type": "json_object"}
            # )
            # result = json.loads(response.choices[0].message.content)

            # Новая реализация Gemini
            system_instruction = "Ты - ассистент для извлечения задач из транскриптов. Отвечай ТОЛЬКО валидным JSON массивом."
            
            # Создаем модель с system instruction для этого запроса
            model_with_instruction = genai.GenerativeModel(
                model_name=settings.GEMINI_MODEL,
                system_instruction=system_instruction
            )
            
            response = model_with_instruction.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=1.0,
                    max_output_tokens=2500,
                    response_mime_type="application/json",
                )
            )

            # Парсим JSON ответ
            result_text = response.text.strip()
            # Убираем markdown код блоки, если они есть
            if result_text.startswith("```json"):
                result_text = result_text[7:]
            if result_text.startswith("```"):
                result_text = result_text[3:]
            if result_text.endswith("```"):
                result_text = result_text[:-3]
            result_text = result_text.strip()
            
            # Попытка исправить незавершенные строки в JSON
            # Ищем незавершенные строки (строки, которые не закрыты кавычками)
            # Заменяем незавершенные строки на пустые строки
            result_text = re.sub(r':\s*"([^"]*?)$', r': ""', result_text, flags=re.MULTILINE)
            # Удаляем незавершенные строки в конце
            result_text = re.sub(r',\s*"([^"]*?)$', '', result_text, flags=re.MULTILINE)
            
            try:
                result = json.loads(result_text)
            except json.JSONDecodeError as json_err:
                logger.warning(f"JSON decode error: {json_err}. Attempting to fix...")
                # Попытка найти и исправить проблемные места
                # Удаляем последнюю незавершенную строку, если она есть
                lines = result_text.split('\n')
                fixed_lines = []
                for i, line in enumerate(lines):
                    # Если строка содержит незавершенную строку (начинается с " но не заканчивается "),
                    # и это не последняя строка массива/объекта
                    if ':' in line and line.count('"') % 2 != 0:
                        # Пытаемся закрыть строку
                        if not line.rstrip().endswith('"') and not line.rstrip().endswith('",'):
                            line = line.rstrip().rstrip(',') + '",'
                    fixed_lines.append(line)
                result_text = '\n'.join(fixed_lines)
                
                try:
                    result = json.loads(result_text)
                except json.JSONDecodeError:
                    logger.error(f"Failed to parse JSON after fix attempt. Raw text: {result_text[:500]}")
                    return []
            
            logger.info(f"Action items extraction completed, extracted {len(result) if isinstance(result, list) else len(result.get('action_items', []))} items")

            if isinstance(result, dict) and "action_items" in result:
                return result["action_items"]
            elif isinstance(result, list):
                return result
            else:
                return []

        except Exception as e:
            logger.error(f"Error extracting action items: {e}", exc_info=True)
            return []

    async def format_transcript(self, transcript_text: str) -> Optional[str]:
        """Форматирование транскрипта в Markdown с подсветкой непонятных слов"""
        # Временно выключено, чтобы не было лишних тегов
        return transcript_text
        
        try:
            if not transcript_text or not transcript_text.strip():
                logger.warning("transcript_text is empty for formatting")
                return transcript_text

            prompt = f"""Ниже приведен текст транскрипта встречи, распознанный через Whisper. 
Встреча может проходить на русском, кыргызском или английском языках (или их смеси).

ТВОЯ ЗАДАЧА:
1. Оформи текст в читаемый Markdown (используй заголовки, списки и абзацы для структурирования).
2. СОХРАНЯЙ ОРИГИНАЛЬНЫЙ ЯЗЫК каждой фразы. Не переводи текст.
3. ЕСЛИ фрагмент текста кажется тебе ошибочно распознанным, бессмысленным или является явной галлюцинацией (например, повторяющиеся фразы или странные термины, не подходящие по смыслу), ОБЯЗАТЕЛЬНО оберни его в HTML тег: <span style="color: red;" class="unclear-word">непонятное слово или фраза</span>.
4. Важно: выделяй только те места, где ты действительно сомневаешься в правильности распознавания.
5. Не удаляй слова из исходного текста, только добавляй оформление.

Транскрипт:
{transcript_text}"""

            system_instruction = "Ты - эксперт по редактированию и структурированию транскриптов встреч на разных языках (RU, KY, EN). Твоя цель - сделать текст максимально читаемым и выделить сомнительные фрагменты транскрибации красным цветом."
            
            model_with_instruction = genai.GenerativeModel(
                model_name=settings.GEMINI_MODEL,
                system_instruction=system_instruction
            )
            
            response = model_with_instruction.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.3, # Меньше креативности, больше точности к исходному тексту
                    max_output_tokens=4000,
                )
            )

            result = response.text
            logger.info(f"Transcript formatting completed, length: {len(result) if result else 0}")
            return result

        except Exception as e:
            logger.error(f"Error formatting transcript: {e}", exc_info=True)
            # В случае ошибки возвращаем хотя бы исходный текст
            return transcript_text

    async def format_segments(self, segments: list[dict]) -> list[dict]:
        """Форматирует отдельные сегменты транскрипта, добавляя теги для непонятных слов"""
        # Временно выключено
        return segments
        
        if not segments:
            return []
            
        try:
            # Превращаем список сегментов в JSON-строку для обработки
            # Оставляем только ID и текст, чтобы сэкономить токены и не запутать модель
            segments_to_process = [{"id": s.get("id"), "text": s.get("text")} for s in segments]
            
            prompt = f"""Ниже приведен список сегментов транскрипта встречи (RU, KY, EN).
Для каждого сегмента проанализируй текст. Если в нем есть ошибки распознавания или галлюцинации, оберни их в тег: <span style="color: red;" class="unclear-word">непонятное слово</span>.

Верни ТОЛЬКО JSON массив объектов с тем же количеством элементов и ID:
[
  {{"id": 0, "text": "обработанный текст"}},
  ...
]

Сегменты:
{json.dumps(segments_to_process, ensure_ascii=False)}"""

            system_instruction = "Ты - ассистент по проверке качества транскрибации. Твоя задача - найти и выделить ошибки в тексте сегментов, вернув JSON результат."
            
            model_with_instruction = genai.GenerativeModel(
                model_name=settings.GEMINI_MODEL,
                system_instruction=system_instruction
            )
            
            response = model_with_instruction.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.1,
                    max_output_tokens=4000,
                    response_mime_type="application/json",
                )
            )

            processed_segments = json.loads(response.text)
            
            # Обновляем оригинальные сегменты
            mapping = {s["id"]: s["text"] for s in processed_segments if "id" in s and "text" in s}
            
            for segment in segments:
                seg_id = segment.get("id")
                if seg_id in mapping:
                    segment["text"] = mapping[seg_id]
                    
            return segments

        except Exception as e:
            logger.error(f"Error formatting segments: {e}", exc_info=True)
            return segments

ai_service = AIService()