# PM Assistant API Documentation

## Базовый URL

```
http://localhost:8000/api
```

## Аутентификация

Все эндпоинты (кроме `/users/login`) требуют аутентификации через session cookie.

### Login

```http
POST /users/login
Content-Type: application/json

{
  "username": "user@domain",
  "password": "password"
}
```

**Response:** Sets `session_id` cookie

### Logout

```http
POST /users/logout
```

### Get Current User

```http
GET /users/me
```

## Проекты

### Получить список проектов

```http
GET /projects/?include_archived=false
```

**Query params:**
- `include_archived` (bool) - включить архивированные проекты

### Получить архивированные проекты

```http
GET /projects/archived
```

### Создать проект

```http
POST /projects/
Content-Type: application/json

{
  "name": "Название проекта",
  "description": "Описание",
  "confluence_data": {"space_key": "SPACE"},
  "jira_data": {"project_key": "PROJ"}
}
```

**Требуется роль:** PM или Manager

### Получить проект

```http
GET /projects/{project_id}
```

### Обновить проект

```http
PUT /projects/{project_id}
Content-Type: application/json

{
  "name": "Новое название",
  "description": "Новое описание"
}
```

**Требуется роль:** PM или Manager

### Архивировать проект

```http
POST /projects/{project_id}/archive
```

**Требуется роль:** PM или Manager

### Разархивировать проект

```http
POST /projects/{project_id}/unarchive
```

**Требуется роль:** PM или Manager

### Удалить проект

```http
DELETE /projects/{project_id}
```

**Требуется роль:** PM или Manager

### Управление доступом

#### Дать доступ пользователю

```http
POST /projects/{project_id}/access
Content-Type: application/json

{
  "user_id": 123,
  "role": "Member"
}
```

**Требуется роль:** PM или Manager

#### Получить список доступов

```http
GET /projects/{project_id}/access
```

#### Отозвать доступ

```http
DELETE /projects/{project_id}/access/{user_id}
```

**Требуется роль:** PM или Manager

## Встречи

### Создать встречу

```http
POST /meetings/
Content-Type: multipart/form-data

title=Название встречи
project_id=1
meeting_date=2025-10-13T10:00:00Z
comments=Комментарии
audio_file=@meeting.mp3
```

**Form fields:**
- `title` (string, required) - название встречи
- `project_id` (int, optional) - ID проекта
- `meeting_date` (datetime, optional) - дата встречи
- `comments` (string, optional) - комментарии
- `audio_file` (file, optional) - аудио файл

### Получить список встреч

```http
GET /meetings/?project_id=1&skip=0&limit=50
```

**Query params:**
- `project_id` (int, optional) - фильтр по проекту
- `skip` (int) - пропустить записей
- `limit` (int) - количество записей (max 100)

**Фильтрация:**
- `organizer_id` (int, optional) - фильтр по организатору встречи
- `start_date` (datetime, optional) - начало периода (ISO 8601 формат)
- `end_date` (datetime, optional) - конец периода (ISO 8601 формат)
- `min_duration` (int, optional) - минимальная длительность в минутах
- `max_duration` (int, optional) - максимальная длительность в минутах

**Сортировка (sort_by):**
- `date_desc` - новые → старые (по умолчанию)
- `date_asc` - старые → новые
- `duration_asc` - от коротких → к длинным
- `duration_desc` - от длинных → к коротким

**Примеры:**

Встречи по организатору:
```http
GET /meetings/?organizer_id=5
```

Встречи за определенный период:
```http
GET /meetings/?start_date=2025-01-01T00:00:00Z&end_date=2025-12-31T23:59:59Z
```

Встречи с определенной длительностью:
```http
GET /meetings/?min_duration=30&max_duration=120
```

Встречи проекта, отсортированные по длительности (от коротких к длинным):
```http
GET /meetings/?project_id=1&sort_by=duration_asc
```

Встречи, отсортированные от новых к старым:
```http
GET /meetings/?sort_by=date_desc
```

Комбинированный фильтр (по организатору, периоду и длительности):
```http
GET /meetings/?organizer_id=5&start_date=2025-01-01T00:00:00Z&end_date=2025-12-31T23:59:59Z&min_duration=30&max_duration=120&sort_by=date_asc
```

### Получить некатегорированные встречи

```http
GET /meetings/uncategorized?skip=0&limit=50
```

### Поиск встреч

```http
GET /meetings/search?q=название&project_id=1
```

**Query params:**
- `q` (string, required) - поисковый запрос
- `project_id` (int, optional) - фильтр по проекту

### Получить детали встречи

```http
GET /meetings/{meeting_id}
```

**Response includes:**
- meeting details
- transcript (if processed)
- summary (if processed)
- notes
- action items

### Обновить встречу

```http
PUT /meetings/{meeting_id}
Content-Type: application/json

{
  "title": "Новое название",
  "project_id": 2,
  "comments": "Обновленные комментарии"
}
```

### Удалить встречу

```http
DELETE /meetings/{meeting_id}
```

### Переместить встречу в другой проект

```http
POST /meetings/{meeting_id}/move?project_id=2
```

**Query params:**
- `project_id` (int, optional) - ID целевого проекта (null для некатегорированных)

### Получить ссылку на аудио

```http
GET /meetings/{meeting_id}/audio-url
```

**Response:**
```json
{
  "url": "https://...",
  "expires_in": 3600
}
```

### Запустить обработку встречи

```http
POST /meetings/{meeting_id}/process
```

**Response:**
```json
{
  "message": "Processing started",
  "job_id": "abc-123",
  "meeting_id": 1
}
```

### Получить статус обработки

```http
GET /meetings/{meeting_id}/processing-status
```

**Response:**
```json
{
  "status": "processing",
  "current_stage": "transcription",
  "progress": 50,
  "error_message": null,
  "started_at": "2025-10-13T10:00:00Z",
  "completed_at": null
}
```

**Статусы:**
- `not_started` - не начата
- `processing` - в процессе
- `completed` - завершена
- `failed` - ошибка

**Этапы обработки:**
- `transcription` - транскрибация
- `summarization` - суммаризация
- `action_items` - извлечение задач
- `completed` - завершено

### Заметки (Notes)

#### Создать заметку

```http
POST /meetings/{meeting_id}/notes
Content-Type: application/json

{
  "content": "Текст заметки"
}
```

#### Получить заметки встречи

```http
GET /meetings/{meeting_id}/notes
```

### Action Items

#### Создать action item

```http
POST /meetings/{meeting_id}/action-items
Content-Type: application/json

{
  "title": "Задача",
  "description": "Описание задачи",
  "assignee_id": 123,
  "due_date": "2025-10-20T00:00:00Z"
}
```

#### Получить action items встречи

```http
GET /meetings/{meeting_id}/action-items
```

## Уведомления

### Получить список уведомлений

```http
GET /notifications/?unread_only=false&skip=0&limit=50
```

**Query params:**
- `unread_only` (bool) - только непрочитанные
- `skip` (int) - пропустить записей
- `limit` (int) - количество записей

### Получить количество непрочитанных

```http
GET /notifications/unread-count
```

**Response:**
```json
{
  "count": 5
}
```

### Отметить как прочитанное

```http
PUT /notifications/{notification_id}/read
```

### Отметить все как прочитанные

```http
POST /notifications/mark-all-read
```

### Удалить уведомление

```http
DELETE /notifications/{notification_id}
```

## Коды ошибок

- `200` - Success
- `201` - Created
- `204` - No Content
- `400` - Bad Request
- `401` - Unauthorized
- `403` - Forbidden
- `404` - Not Found
- `500` - Internal Server Error

## Примеры фильтрации и сортировки встреч

### Сценарий 1: Все встречи пользователя, отсортированные от новых к старым (по умолчанию)

```bash
curl "http://localhost:8000/api/meetings/" \
  -H "Cookie: session_id=YOUR_SESSION"
```

### Сценарий 2: Встречи, отсортированные от старых к новым

```bash
curl "http://localhost:8000/api/meetings/?sort_by=date_asc" \
  -H "Cookie: session_id=YOUR_SESSION"
```

### Сценарий 3: Встречи определенного организатора

```bash
curl "http://localhost:8000/api/meetings/?organizer_id=5" \
  -H "Cookie: session_id=YOUR_SESSION"
```

### Сценарий 4: Встречи за определенный период (квартал 2025)

```bash
curl "http://localhost:8000/api/meetings/?start_date=2025-01-01T00:00:00Z&end_date=2025-03-31T23:59:59Z" \
  -H "Cookie: session_id=YOUR_SESSION"
```

### Сценарий 5: Короткие встречи (менее 30 минут)

```bash
curl "http://localhost:8000/api/meetings/?max_duration=30" \
  -H "Cookie: session_id=YOUR_SESSION"
```

### Сценарий 6: Долгие встречи (более 60 минут), отсортированные по возрастанию длительности

```bash
curl "http://localhost:8000/api/meetings/?min_duration=60&sort_by=duration_asc" \
  -H "Cookie: session_id=YOUR_SESSION"
```

### Сценарий 7: Встречи проекта, отсортированные по длительности (от длинных к коротким)

```bash
curl "http://localhost:8000/api/meetings/?project_id=1&sort_by=duration_desc" \
  -H "Cookie: session_id=YOUR_SESSION"
```

### Сценарий 8: Комплексный фильтр (проект, организатор, период, длительность, сортировка)

```bash
curl "http://localhost:8000/api/meetings/?project_id=1&organizer_id=5&start_date=2025-01-01T00:00:00Z&end_date=2025-12-31T23:59:59Z&min_duration=30&max_duration=120&sort_by=date_desc" \
  -H "Cookie: session_id=YOUR_SESSION"
```

### Сценарий 9: С пагинацией - вторая страница по 20 элементов

```bash
curl "http://localhost:8000/api/meetings/?skip=20&limit=20&sort_by=date_desc" \
  -H "Cookie: session_id=YOUR_SESSION"
```

## Типы уведомлений

- `

## Meeting Processing Status

### Получить статус обработки встречи

```
GET /api/meetings/{meeting_id}/processing-status
```

**Параметры:**
- `meeting_id` (path): ID встречи

**Авторизация:** Требуется (cookie session)

**Описание:**
Возвращает текущий статус обработки встречи (транскрибация, суммаризация, извлечение задач).

**Возвращаемые поля:**
- `meeting_id`: ID встречи
- `status`: Статус обработки
  - `"not_started"` - обработка еще не начиналась
  - `"processing"` - идет обработка
  - `"completed"` - обработка завершена успешно
  - `"failed"` - обработка завершилась ошибкой
- `current_stage`: Текущий этап обработки
  - `"transcription"` - транскрибация аудио
  - `"summarization"` - создание резюме
  - `"action_items"` - извлечение задач
- `progress`: Процент выполнения (0-100)
- `error_message`: Текст ошибки (если есть)
- `started_at`: Время начала обработки (ISO 8601)
- `completed_at`: Время завершения обработки (ISO 8601)
- `estimated_completion`: Приблизительное время завершения (ISO 8601)
- `stage_info`: Описание текущего этапа на русском языке

**Пример запроса:**
```bash
curl -X GET "http://localhost:8000/api/meetings/1/processing-status" \
  -H "Cookie: session_id=your_session_id"
```

**Пример ответа (обработка идет):**
```json
{
  "meeting_id": 1,
  "status": "processing",
  "current_stage": "transcription",
  "progress": 35,
  "error_message": null,
  "started_at": "2025-10-27T12:00:00Z",
  "completed_at": null,
  "estimated_completion": "2025-10-27T12:05:30Z",
  "stage_info": "Транскрибация аудио"
}
```

**Пример ответа (завершено):**
```json
{
  "meeting_id": 1,
  "status": "completed",
  "current_stage": "action_items",
  "progress": 100,
  "error_message": null,
  "started_at": "2025-10-27T12:00:00Z",
  "completed_at": "2025-10-27T12:10:45Z",
  "estimated_completion": null,
  "stage_info": "Извлечение задач"
}
```

**Пример ответа (ошибка):**
```json
{
  "meeting_id": 1,
  "status": "failed",
  "current_stage": "transcription",
  "progress": 25,
  "error_message": "Failed to download audio file from S3",
  "started_at": "2025-10-27T12:00:00Z",
  "completed_at": "2025-10-27T12:02:15Z",
  "estimated_completion": null,
  "stage_info": "Транскрибация аудио"
}
```

**Пример ответа (не начиналась):**
```json
{
  "meeting_id": 1,
  "status": "not_started",
  "current_stage": null,
  "progress": 0,
  "error_message": null,
  "started_at": null,
  "completed_at": null,
  "estimated_completion": null,
  "message": "Обработка еще не начиналась"
}
```

### Этапы обработки встречи

1. **Transcription (10% → 50%)**
   - Скачивание аудио файла из S3
   - Отправка на Whisper (локальный или OpenAI)
   - Сохранение транскрипта с временными метками

2. **Summarization (50% → 80%)**
   - Анализ транскрипта
   - Создание резюме встречи с помощью GPT-4
   - Сохранение резюме в БД

3. **Action Items (80% → 100%)**
   - Извлечение задач и назначений
   - Создание action items с описаниями
   - Завершение обработки

### Полинг статуса (Polling)

Рекомендуется проверять статус каждые 2-5 секунд:

```javascript
async function checkProcessingStatus(meetingId) {
  const response = await fetch(`/api/meetings/${meetingId}/processing-status`, {
    method: 'GET',
    credentials: 'include'
  });
  
  const data = await response.json();
  
  console.log(`Status: ${data.status}`);
  console.log(`Progress: ${data.progress}%`);
  console.log(`Stage: ${data.stage_info}`);
  
  if (data.status === 'completed') {
    console.log('✓ Обработка завершена!');
  } else if (data.status === 'failed') {
    console.error('✗ Ошибка:', data.error_message);
  } else if (data.estimated_completion) {
    const eta = new Date(data.estimated_completion);
    console.log(`ETA: ${eta.toLocaleTimeString()}`);
  }
}

// Проверять каждые 3 секунды
setInterval(() => checkProcessingStatus(1), 3000);
```

### Python пример

```python
import requests
import time

def check_meeting_status(meeting_id, session_id):
    url = f"http://localhost:8000/api/meetings/{meeting_id}/processing-status"
    cookies = {"session_id": session_id}
    
    while True:
        response = requests.get(url, cookies=cookies)
        data = response.json()
        
        print(f"Status: {data['status']}")
        print(f"Progress: {data['progress']}%")
        print(f"Stage: {data['stage_info']}")
        
        if data['status'] == 'completed':
            print("✓ Processing completed!")
            break
        elif data['status'] == 'failed':
            print(f"✗ Error: {data['error_message']}")
            break
        
        if data['estimated_completion']:
            print(f"ETA: {data['estimated_completion']}")
        
        print("---")
        time.sleep(3)  # Check every 3 seconds

# Usage
check_meeting_status(meeting_id=1, session_id="your_session_id")
```

### WebSocket Polling (Advanced)

Для real-time обновлений рекомендуется использовать WebSocket вместо HTTP polling для уменьшения нагрузки на сервер.


## Meeting Duration

### Получить информацию о длительности встречи

```
GET /api/meetings/{meeting_id}/duration
```

**Параметры:**
- `meeting_id` (path): ID встречи

**Авторизация:** Требуется (cookie session)

**Описание:**
Возвращает информацию о длительности встречи в минутах и секундах, а также источник этой информации.

**Возвращаемые поля:**
- `meeting_id`: ID встречи
- `duration`: Длительность в минутах (может быть null если не установлена)
- `duration_seconds`: Длительность в секундах
- `audio_file_size`: Размер аудиофайла в байтах
- `source`: Источник информации
  - `"transcription"` - определена из транскрипта
  - `"manual"` - установлена вручную
  - `"unknown"` - источник неизвестен
- `processing_status`: Статус обработки встречи

**Пример запроса:**
```bash
curl -X GET "http://localhost:8000/api/meetings/1/duration" \
  -H "Cookie: session_id=your_session_id"
```

**Пример ответа:**
```json
{
  "meeting_id": 1,
  "duration": 45,
  "duration_seconds": 2700,
  "audio_file_size": 5242880,
  "source": "transcription",
  "processing_status": "completed"
}
```

### Обновить длительность встречи

```
PUT /api/meetings/{meeting_id}/duration?duration_minutes=45
```

**Параметры:**
- `meeting_id` (path): ID встречи
- `duration_minutes` (query): Длительность в минутах (целое число, минимум 1)

**Авторизация:** Требуется (только организатор встречи)

**Описание:**
Обновляет длительность встречи вручную. Может использоваться если:
- Автоматическое определение длительности не сработало
- Нужно исправить длительность
- Встреча без аудиофайла

**Пример запроса:**
```bash
curl -X PUT "http://localhost:8000/api/meetings/1/duration?duration_minutes=45" \
  -H "Cookie: session_id=your_session_id"
```

**Пример ответа:**
```json
{
  "meeting_id": 1,
  "duration": 45,
  "duration_seconds": 2700,
  "previous_duration": null,
  "message": "Duration updated successfully from None to 45 minutes"
}
```

### Как определяется длительность

1. **При загрузке встречи:**
   - Если указана длительность в форме → используется она
   - Иначе → остается пустой (null)

2. **При обработке транскрипции:**
   - Whisper API возвращает длительность аудио
   - Система автоматически сохраняет её в минутах
   - Преобразование: если > 100 секунд, делится на 60

3. **Ручное обновление:**
   - Организатор может установить длительность через PUT endpoint
   - Минимум 1 минута, целое число


## Users - Пользователи

### Получить список пользователей с поиском

```
GET /api/users/
```

**Query parameters:**
- `search` (string, optional): Поиск по имени (first_name), фамилии (last_name) или логину (ad_account)
- `skip` (integer, default=0): Смещение для пагинации
- `limit` (integer, default=100): Количество результатов на странице (max=1000)

**Авторизация:** Требуется (для всех аутентифицированных пользователей)

**Описание:**
Возвращает список пользователей с поддержкой поиска и пагинации. Поиск работает по:
- Имени (first_name)
- Фамилии (last_name)
- Логину AD (ad_account)

**Пример запросов:**

```bash
# Все пользователи
curl -X GET "http://localhost:8000/api/users/" \
  -H "Cookie: session_id=your_session_id"

# Поиск по имени "John"
curl -X GET "http://localhost:8000/api/users/?search=john" \
  -H "Cookie: session_id=your_session_id"

# Поиск по фамилии "Doe"
curl -X GET "http://localhost:8000/api/users/?search=doe" \
  -H "Cookie: session_id=your_session_id"

# Поиск по логину "jdoe"
curl -X GET "http://localhost:8000/api/users/?search=jdoe" \
  -H "Cookie: session_id=your_session_id"

# Поиск с пагинацией
curl -X GET "http://localhost:8000/api/users/?search=john&skip=50&limit=25" \
  -H "Cookie: session_id=your_session_id"
```

**Пример ответа:**
```json
{
  "users": [
    {
      "id": 1,
      "ad_account": "jdoe",
      "first_name": "John",
      "last_name": "Doe",
      "role": "Manager",
      "is_active": true,
      "created_at": "2025-10-27T10:00:00Z",
      "updated_at": "2025-10-27T12:00:00Z"
    },
    {
      "id": 2,
      "ad_account": "jsmith",
      "first_name": "John",
      "last_name": "Smith",
      "role": "Member",
      "is_active": true,
      "created_at": "2025-10-26T10:00:00Z",
      "updated_at": "2025-10-26T12:00:00Z"
    }
  ],
  "total": 2
}
```

### Получить информацию о конкретном пользователе

```
GET /api/users/{user_id}
```

**Параметры:**
- `user_id` (path): ID пользователя

**Авторизация:** Требуется (для всех аутентифицированных пользователей)

**Пример ответа:**
```json
{
  "id": 1,
  "ad_account": "jdoe",
  "first_name": "John",
  "last_name": "Doe",
  "role": "Manager",
  "is_active": true,
  "created_at": "2025-10-27T10:00:00Z",
  "updated_at": "2025-10-27T12:00:00Z"
}
```

### Обновить роль пользователя

```
PUT /api/users/{user_id}/role?role=Backend%20Dev
```

**Параметры:**
- `user_id` (path): ID пользователя
- `role` (query): Новая роль (Member, PM, Manager, Backend Dev, Frontend Dev, Designer, QA)

**Авторизация:** Требуется (только Manager)

**Пример:**
```bash
curl -X PUT "http://localhost:8000/api/users/5/role?role=Backend%20Dev" \
  -H "Cookie: session_id=your_session_id"
```