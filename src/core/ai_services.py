from openai import OpenAI
from typing import Optional, BinaryIO
import json
import httpx
from io import BytesIO
import logging
import soundfile as sf
import numpy as np
import tempfile
import os

from src.core.config import settings

logger = logging.getLogger(__name__)


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
        wav_path = None
        tmp_path = None
        try:
            # Читаем аудио файл
            audio_file.seek(0)
            audio_bytes = audio_file.read()
            
            # Создаем временный файл для сохранения исходного аудио
            with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
                tmp_path = tmp_file.name
                tmp_file.write(audio_bytes)
            
            try:
                # Используем librosa для универсального чтения аудио (поддерживает MP3, WAV, FLAC, etc.)
                import librosa
                data, samplerate = librosa.load(tmp_path, sr=None, mono=True)
                logger.info(f"Audio loaded with librosa: samplerate={samplerate}, shape={data.shape}")
                
                # Преобразуем в WAV формат для отправки на OpenAI
                with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp_wav:
                    wav_path = tmp_wav.name
                
                # Убеждаемся, что данные в правильном формате для soundfile (float32 и в диапазоне [-1, 1])
                data = np.asarray(data, dtype=np.float32)
                max_val = np.max(np.abs(data))
                if max_val > 0:
                    data = data / max_val
                
                sf.write(wav_path, data, samplerate, format='WAV', subtype='PCM_16')
                logger.info(f"WAV file written successfully: {wav_path}")
                
                with open(wav_path, 'rb') as wav_file:
                    transcript = self.client.audio.transcriptions.create(
                        model=settings.WHISPER_MODEL,
                        file=(filename.replace('.mp3', '.wav'), wav_file),
                        response_format="verbose_json",
                        timestamp_granularities=["word", "segment"]
                    )
                
                if wav_path and os.path.exists(wav_path):
                    os.unlink(wav_path)
                result = transcript.model_dump()
                logger.debug(f"OpenAI Whisper response keys: {result.keys() if isinstance(result, dict) else 'not a dict'}")
                return result
            finally:
                if tmp_path and os.path.exists(tmp_path):
                    os.unlink(tmp_path)
                
        except Exception as e:
            logger.error(f"Error transcribing audio with OpenAI: {e}", exc_info=True)
            return None

    async def _transcribe_local_whisper(self, audio_file: BinaryIO, filename: str = "audio.mp3") -> Optional[dict]:
        """Транскрибация через локальный Whisper сервер"""
        wav_path = None
        tmp_path = None
        try:
            # Читаем аудио файл
            audio_file.seek(0)
            audio_bytes = audio_file.read()
            
            # Создаем временный файл для сохранения исходного аудио
            with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
                tmp_path = tmp_file.name
                tmp_file.write(audio_bytes)
            
            try:
                # Используем librosa для универсального чтения аудио (поддерживает MP3, WAV, FLAC, etc.)
                import librosa
                data, samplerate = librosa.load(tmp_path, sr=None, mono=False)
                logger.info(f"Audio loaded with librosa: samplerate={samplerate}, duration={len(data)/samplerate:.2f}s if mono else dur={(len(data[0])/samplerate if isinstance(data, np.ndarray) and len(data.shape) > 1 else len(data)/samplerate):.2f}s")
                
                # Переписываем в единый формат для Whisper (mono, 16kHz)
                with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp_wav:
                    wav_path = tmp_wav.name
                
                # Конвертируем в моно если нужно
                if len(data.shape) > 1:
                    data = np.mean(data, axis=1)
                
                # Переискателируем если нужно
                target_sr = 16000
                if samplerate != target_sr:
                    data = librosa.resample(data, orig_sr=samplerate, target_sr=target_sr)
                    samplerate = target_sr
                
                # Убеждаемся, что данные в правильном формате для soundfile (float32 и в диапазоне [-1, 1])
                data = np.asarray(data, dtype=np.float32)
                max_val = np.max(np.abs(data))
                if max_val > 0:
                    data = data / max_val
                
                sf.write(wav_path, data, samplerate, format='WAV', subtype='PCM_16')
                logger.info(f"WAV file written successfully: {wav_path}")
                
                # Отправляем на Whisper сервер
                with open(wav_path, 'rb') as wav_file:
                    wav_bytes = wav_file.read()
                
                async with httpx.AsyncClient(timeout=600) as client:
                    files = {"file": (filename.replace('.mp3', '.wav'), wav_bytes)}
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
                    
            finally:
                if tmp_path and os.path.exists(tmp_path):
                    os.unlink(tmp_path)
                if wav_path and os.path.exists(wav_path):
                    os.unlink(wav_path)
                    
        except Exception as e:
            logger.error(f"Error transcribing audio with local Whisper: {e}", exc_info=True)
            return None

    async def summarize_transcript(self, transcript_text: str, meeting_title: str = "") -> Optional[str]:
        """Суммаризация транскрипта через ChatGPT"""
        try:
            if not transcript_text or not transcript_text.strip():
                logger.warning("transcript_text is empty")
                return "Нет текста для суммаризации"
            
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

            logger.info(f"Sending summarization request to {settings.GPT_MODEL}...")
            logger.debug(f"API Key present: {bool(settings.OPENAI_API_KEY)}, Transcript length: {len(transcript_text)}")
            
            response = self.client.chat.completions.create(
                model=settings.GPT_MODEL,
                messages=[
                    {"role": "system", "content": "Ты - профессиональный ассистент для менеджеров проектов. Твоя задача - создавать краткие и структурированные резюме встреч на русском языке."},
                    {"role": "user", "content": prompt}
                ],
                temperature=1,
                max_completion_tokens=1000
            )
            logger.info("Summarization response received successfully")
            result = response.choices[0].message.content
            logger.debug(f"Summary result: {result[:100]}..." if result else "Summary result is None")
            return result
        except Exception as e:
            logger.error(f"Error summarizing transcript: {type(e).__name__}: {str(e)}", exc_info=True)
            logger.error(f"Full exception details:", exc_info=True)
            return None

    async def extract_action_items(self, transcript_text: str) -> Optional[list[dict]]:
        """Извлечение action items из транскрипта"""
        try:
            if not transcript_text or not transcript_text.strip():
                logger.warning("transcript_text is empty for action items extraction")
                return []
            
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

            logger.info(f"Sending action items extraction request to {settings.GPT_MODEL}...")
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
            
            logger.info("Action items response received successfully")
            result = json.loads(response.choices[0].message.content)
            # ChatGPT может вернуть объект с ключом "action_items" или массив напрямую
            if isinstance(result, dict) and "action_items" in result:
                return result["action_items"]
            elif isinstance(result, list):
                return result
            else:
                return []
        except Exception as e:
            logger.error(f"Error extracting action items: {e}", exc_info=True)
            return []


ai_service = AIService()

