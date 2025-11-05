"""Модуль для генерации PDF документов из встреч"""
from io import BytesIO
from typing import Optional
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
from reportlab.pdfbase import pdfmetrics
import logging

logger = logging.getLogger(__name__)

# Попытка зарегистрировать шрифт для поддержки кириллицы
try:
    # Пробуем использовать встроенный шрифт DejaVu Sans или Helvetica
    pdfmetrics.registerFontFamily('Helvetica', normal='Helvetica', bold='Helvetica-Bold')
except Exception as e:
    logger.warning(f"Could not register custom font: {e}")


def generate_meeting_pdf(
    title: str,
    meeting_date: datetime,
    duration: Optional[int],
    transcript: Optional[str],
    summary: Optional[str],
    notes: list[dict],
    organizer_name: Optional[str] = None
) -> BytesIO:
    """
    Генерирует PDF документ из данных встречи
    
    Args:
        title: Название встречи
        meeting_date: Дата встречи
        duration: Длительность в секундах
        transcript: Текст транскрипта
        summary: Текст суммаризации
        notes: Список заметок (каждая с полями content, created_at)
        organizer_name: Имя организатора
        
    Returns:
        BytesIO объект с PDF данными
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    story = []
    
    # Стили
    styles = getSampleStyleSheet()
    
    # Создаем кастомные стили
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=18,
        textColor=(0, 0, 0),
        spaceAfter=12,
        alignment=TA_CENTER
    )
    
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=14,
        textColor=(0.2, 0.2, 0.2),
        spaceAfter=8,
        spaceBefore=12,
        alignment=TA_LEFT
    )
    
    body_style = ParagraphStyle(
        'CustomBody',
        parent=styles['BodyText'],
        fontSize=11,
        textColor=(0.1, 0.1, 0.1),
        spaceAfter=10,
        alignment=TA_JUSTIFY,
        leading=14
    )
    
    meta_style = ParagraphStyle(
        'CustomMeta',
        parent=styles['BodyText'],
        fontSize=10,
        textColor=(0.4, 0.4, 0.4),
        spaceAfter=15,
        alignment=TA_LEFT
    )
    
    # Заголовок
    story.append(Paragraph(title, title_style))
    story.append(Spacer(1, 0.2 * inch))
    
    # Метаинформация
    meta_info = []
    if organizer_name:
        meta_info.append(f"<b>Организатор:</b> {organizer_name}")
    if meeting_date:
        formatted_date = meeting_date.strftime("%d.%m.%Y %H:%M")
        meta_info.append(f"<b>Дата:</b> {formatted_date}")
    if duration:
        hours = duration // 3600
        minutes = (duration % 3600) // 60
        duration_str = f"{hours:02d}:{minutes:02d}:{duration % 60:02d}" if hours > 0 else f"{minutes:02d}:{duration % 60:02d}"
        meta_info.append(f"<b>Длительность:</b> {duration_str}")
    
    if meta_info:
        story.append(Paragraph(" | ".join(meta_info), meta_style))
        story.append(Spacer(1, 0.2 * inch))
    
    # Разделитель
    story.append(Spacer(1, 0.1 * inch))
    
    # Суммаризация
    if summary:
        story.append(Paragraph("Резюме встречи", heading_style))
        # Очищаем текст от HTML тегов и специальных символов для безопасного отображения
        summary_text = _clean_text(summary)
        story.append(Paragraph(summary_text, body_style))
        story.append(Spacer(1, 0.2 * inch))
    
    # Заметки
    if notes:
        story.append(Paragraph("Заметки", heading_style))
        for idx, note in enumerate(notes, 1):
            note_content = note.get('content', '')
            note_date = note.get('created_at')
            
            note_text = f"<b>Заметка {idx}</b>"
            if note_date:
                try:
                    if isinstance(note_date, str):
                        note_date_obj = datetime.fromisoformat(note_date.replace('Z', '+00:00'))
                    else:
                        note_date_obj = note_date
                    formatted_date = note_date_obj.strftime("%d.%m.%Y %H:%M")
                    note_text += f" <i>({formatted_date})</i>"
                except Exception:
                    pass
            
            story.append(Paragraph(note_text, ParagraphStyle(
                'NoteHeader',
                parent=styles['BodyText'],
                fontSize=10,
                textColor=(0.3, 0.3, 0.3),
                spaceAfter=4
            )))
            
            note_content_clean = _clean_text(note_content)
            story.append(Paragraph(note_content_clean, body_style))
            story.append(Spacer(1, 0.15 * inch))
        
        story.append(Spacer(1, 0.2 * inch))
    
    # Транскрипт
    if transcript:
        story.append(PageBreak())
        story.append(Paragraph("Транскрипт встречи", heading_style))
        transcript_clean = _clean_text(transcript)
        story.append(Paragraph(transcript_clean, body_style))
    
    # Строим PDF
    doc.build(story)
    buffer.seek(0)
    
    logger.info(f"PDF generated successfully for meeting: {title}")
    return buffer


def _clean_text(text: str) -> str:
    """
    Очищает текст от HTML тегов и специальных символов,
    экранирует символы для reportlab
    """
    if not text:
        return ""
    
    # Удаляем HTML теги (простой способ)
    import re
    text = re.sub(r'<[^>]+>', '', text)
    
    # Экранируем специальные символы для reportlab
    text = text.replace('&', '&amp;')
    text = text.replace('<', '&lt;')
    text = text.replace('>', '&gt;')
    
    # Заменяем множественные пробелы на одинарные
    text = re.sub(r'\s+', ' ', text)
    
    return text.strip()

