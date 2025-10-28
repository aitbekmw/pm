import io
import logging
import numpy as np
from typing import Tuple, Optional
import librosa
import soundfile as sf

logger = logging.getLogger(__name__)

# Рекомендуемая частота дискретизации
REQUIRED_SR = 16000


class AudioPreprocessor:
    """Класс для предобработки аудиофайлов"""
    
    @staticmethod
    def load_audio_safe(audio_bytes: bytes, sr: int = REQUIRED_SR) -> Optional[Tuple[np.ndarray, int]]:
        """
        Безопасная загрузка аудиофайла с обработкой ошибок
        
        Args:
            audio_bytes: байты аудиофайла
            sr: целевая частота дискретизации
            
        Returns:
            Кортеж (аудиоданные, частота дискретизации) или None при ошибке
        """
        try:
            audio_data, sr_native = librosa.load(io.BytesIO(audio_bytes), sr=sr, mono=True)
            return audio_data, sr
        except Exception as e:
            logger.warning(f"Ошибка при загрузке аудио стандартным методом: {e}")
            
            # Пытаемся исправить поврежденный MP3
            try:
                audio_data, sr_native = AudioPreprocessor._repair_mp3(audio_bytes, sr)
                if audio_data is not None:
                    logger.info("Аудио успешно восстановлено после повреждения")
                    return audio_data, sr
            except Exception as e2:
                logger.warning(f"Ошибка при восстановлении MP3: {e2}")
            
            # Последняя попытка - извлечение валидных фреймов
            try:
                audio_data, sr_native = AudioPreprocessor._extract_valid_frames(audio_bytes, sr)
                if audio_data is not None:
                    logger.info("Валидные фреймы успешно извлечены из аудио")
                    return audio_data, sr
            except Exception as e3:
                logger.error(f"Не удалось загрузить аудио даже после восстановления: {e3}")
            
            return None
    
    @staticmethod
    def _repair_mp3(audio_bytes: bytes, sr: int = REQUIRED_SR) -> Optional[Tuple[np.ndarray, int]]:
        """
        Попытка восстановить поврежденный MP3 файл
        путем преобразования в WAV и повторной загрузки
        
        Args:
            audio_bytes: байты MP3 файла
            sr: целевая частота дискретизации
            
        Returns:
            Кортеж (аудиоданные, частота дискретизации) или None
        """
        try:
            # Пытаемся загрузить как есть, но с низкими требованиями
            audio_data, sr_native = librosa.load(
                io.BytesIO(audio_bytes), 
                sr=None,  # Не переконвертируем
                mono=True
            )
            
            # Переконвертируем в целевую частоту
            if sr_native != sr:
                audio_data = librosa.resample(audio_data, orig_sr=sr_native, target_sr=sr)
            
            return audio_data, sr
        except Exception as e:
            logger.debug(f"Не удалось восстановить MP3 переконвертацией: {e}")
            return None
    
    @staticmethod
    def _extract_valid_frames(audio_bytes: bytes, sr: int = REQUIRED_SR) -> Optional[Tuple[np.ndarray, int]]:
        """
        Извлечение валидных фреймов из поврежденного аудио
        путем поиска синхронизационных меток MP3
        
        Args:
            audio_bytes: байты MP3 файла
            sr: целевая частота дискретизации
            
        Returns:
            Кортеж (аудиоданные, частота дискретизации) или None
        """
        # MP3 синхронизационная метка начинается с 11 бит, установленных в 1 (0xFFF)
        sync_marker = b'\xFF\xFB'  # MPEG Layer III, no CRC
        
        frames = []
        offset = 0
        
        while offset < len(audio_bytes):
            idx = audio_bytes.find(sync_marker, offset)
            if idx == -1:
                break
            
            try:
                # Пытаемся прочитать фрейм (~418 байт для 128kbps)
                frame_end = min(idx + 418, len(audio_bytes))
                frame = audio_bytes[idx:frame_end]
                
                if len(frame) >= 4:
                    frames.append(frame)
                
                offset = idx + 2
            except Exception as e:
                logger.debug(f"Ошибка при извлечении фрейма: {e}")
                offset = idx + 2
        
        if frames:
            # Объединяем восстановленные фреймы
            repaired_data = b''.join(frames)
            
            try:
                audio_data, sr_native = librosa.load(
                    io.BytesIO(repaired_data),
                    sr=sr,
                    mono=True
                )
                return audio_data, sr
            except Exception as e:
                logger.debug(f"Не удалось загрузить восстановленные фреймы: {e}")
        
        return None
    
    @staticmethod
    def preprocess_audio(audio_bytes: bytes, sr: int = REQUIRED_SR) -> Optional[bytes]:
        """
        Полная предобработка аудиофайла:
        - Загрузка с восстановлением ошибок
        - Нормализация уровня громкости
        - Применение фильтра для удаления фонового шума
        - Сохранение в формате WAV
        
        Args:
            audio_bytes: исходные байты аудиофайла
            sr: целевая частота дискретизации
            
        Returns:
            Обработанные байты аудиофайла в формате WAV или None
        """
        # Загружаем аудио
        result = AudioPreprocessor.load_audio_safe(audio_bytes, sr)
        if result is None:
            logger.error("Не удалось загрузить аудиофайл даже после восстановления")
            return None
        
        audio_data, sr_loaded = result
        
        # Нормализуем уровень громкости
        audio_data = AudioPreprocessor._normalize_audio(audio_data)
        
        # Применяем фильтр для удаления фонового шума (опционально)
        # audio_data = AudioPreprocessor._reduce_noise(audio_data, sr_loaded)
        
        # Сохраняем в формат WAV
        output = io.BytesIO()
        sf.write(output, audio_data, sr_loaded, format='WAV')
        output.seek(0)
        
        return output.getvalue()
    
    @staticmethod
    def _normalize_audio(audio_data: np.ndarray, target_db: float = -20.0) -> np.ndarray:
        """
        Нормализуем аудио до целевого уровня dB
        
        Args:
            audio_data: аудиоданные
            target_db: целевой уровень в dB
            
        Returns:
            Нормализованные аудиоданные
        """
        # Вычисляем текущий RMS
        rms = np.sqrt(np.mean(audio_data ** 2))
        
        if rms > 0:
            # Конвертируем целевой dB в линейный масштаб
            target_linear = 10 ** (target_db / 20.0)
            
            # Применяем коэффициент усиления
            audio_data = audio_data * (target_linear / rms)
            
            # Предотвращаем клиппинг
            max_val = np.max(np.abs(audio_data))
            if max_val > 1.0:
                audio_data = audio_data / max_val
        
        return audio_data
    
    @staticmethod
    def _reduce_noise(audio_data: np.ndarray, sr: int, n_fft: int = 2048) -> np.ndarray:
        """
        Простое удаление фонового шума
        
        Args:
            audio_data: аудиоданные
            sr: частота дискретизации
            n_fft: размер FFT
            
        Returns:
            Аудиоданные с ослабленным шумом
        """
        # Вычисляем спектрограмму
        S = librosa.stft(audio_data, n_fft=n_fft)
        S_db = librosa.power_to_db(np.abs(S) ** 2, ref=np.max)
        
        # Находим пороговое значение для шума (нижний квартиль)
        threshold = np.percentile(S_db, 25)
        
        # Применяем маску
        mask = librosa.power_to_db(np.abs(S) ** 2, ref=np.max) > threshold
        S_denoised = S * mask
        
        # Восстанавливаем аудио
        audio_denoised = librosa.istft(S_denoised)
        
        return audio_denoised


# Глобальный экземпляр
audio_preprocessor = AudioPreprocessor()
