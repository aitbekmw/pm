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

## Типы уведомлений

- `processing` - Обработка встречи начата
- `completed` - Обработка завершена
- `failed` - Ошибка обработки

## Роли пользователей

- `PM` - Project Manager (все права)
- `Manager` - Manager (создание проектов, управление доступом)
- `Member` - Member (просмотр, создание встреч)

## Права доступа

| Функция | PM | Manager | Member |
|---------|----|---------| -------|
| Создание проектов | ✅ | ✅ | ❌ |
| Удаление проектов | ✅ | ✅ | ❌ |
| Архивирование | ✅ | ✅ | ❌ |
| Управление доступом | ✅ | ✅ | ❌ |
| Создание встреч | ✅ | ✅ | ✅ |
| Просмотр встреч | ✅ | ✅ | ✅ |

