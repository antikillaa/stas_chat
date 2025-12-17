# Docker Setup для Stas Chat

## Варианты запуска

### 1. С локальным LM Studio (рекомендуется)
Для работы с вашей моделью `openai/gpt-oss-20b`:

**Требования:**
- LM Studio запущен на порту 1234
- Модель `openai/gpt-oss-20b` загружена и активна
- Сервер в LM Studio настроен на `0.0.0.0:1234`

```bash
# Запуск только бота (подключается к LM Studio на хосте)
docker-compose -f docker-compose.local.yml up --build
```

### 2. С Ollama в контейнере
Полная изолированная среда с легкой моделью:

```bash
# Запуск бота + Ollama с автоматической загрузкой модели phi
docker-compose up --build
```

## Быстрый старт (LM Studio)

1. Запустите LM Studio и загрузите модель `openai/gpt-oss-20b`
2. Включите сервер на порту 1234 с адресом `0.0.0.0:1234`
3. Убедитесь, что `.env` файл настроен:
```
TG_TOKEN=your_telegram_bot_token
HF_TOKEN=placeholder
AI_MODEL=openai/gpt-oss-20b
```

4. Запустите бота:
```bash
docker-compose -f docker-compose.local.yml up --build
```

## Быстрый старт (Ollama)

1. Настройте `.env`:
```
TG_TOKEN=your_telegram_bot_token
HF_TOKEN=placeholder
AI_MODEL=phi
```

2. Запустите:
```bash
docker-compose up --build
```

## Команды управления

```bash
# Для LM Studio версии
docker-compose -f docker-compose.local.yml down
docker-compose -f docker-compose.local.yml up --build

# Для Ollama версии
docker-compose down
docker-compose up --build

# Логи
docker-compose logs -f telegram-bot

# Пересборка без кеша
docker-compose build --no-cache telegram-bot
```

## Файлы конфигурации

- `docker-compose.local.yml` - для работы с локальным LM Studio
- `docker-compose.yml` - для полностью контейнеризованной среды с Ollama
- `persona.txt` - монтируется как volume для быстрого редактирования

## Устранение проблем

**Модель не найдена:**
- Убедитесь, что модель загружена и активна в LM Studio
- Проверьте, что сервер LM Studio слушает на `0.0.0.0:1234`

**Контейнер не подключается к LM Studio:**
- Используйте `host.docker.internal:1234` вместо `localhost:1234`
- Проверьте, что порт 1234 не заблокирован файрволом