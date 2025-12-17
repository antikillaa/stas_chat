# Stas Chat

A Telegram bot that replies in the user's style using a local LM. The bot loads a persona from `persona.txt`, keeps a short conversation history per chat, and supports both LM Studio and containerized deployment.

## Features
- Style-preserving replies using a persona file
- Conversation history (limited to 20 messages by default)
- Two reply modes: `stylish` (short) and `detailed` (long)
- Simple media praise logic
- Commands: `/reset` and `/mode` for chat control
- Docker support with two deployment options

## Quick Start Options

### Option 1: Docker + Local LM Studio (Recommended)
Best for using your existing `openai/gpt-oss-20b` model:

```bash
# Start LM Studio with openai/gpt-oss-20b on port 1234
# Then run:
cd docker
docker-compose -f docker-compose.local.yml up --build
```

### Option 2: Full Docker with Ollama
Completely containerized with lightweight model:

```bash
cd docker
docker-compose up --build
```

### Option 3: Local Python Development
Traditional setup for development:

```bash
python -m venv .venv
source .venv/bin/activate  # macOS/Linux
pip install -r requirements.txt
python bot.py
```

## Files Structure
- `bot.py` — main bot implementation
- `persona.txt` — persona text used to emulate your style
- `.env` — environment variables
- `requirements.txt` — Python dependencies
- `docker/` — Docker configurations
  - `docker-compose.local.yml` — for LM Studio integration
  - `docker-compose.yml` — full containerized setup
  - `DOCKER.md` — detailed Docker instructions

## Environment Variables (`.env`)
```env
TG_TOKEN=your_telegram_bot_token
HF_TOKEN=placeholder_token
AI_MODEL=openai/gpt-oss-20b  # or phi for Ollama
LM_STUDIO_URL=http://127.0.0.1:1234/v1  # optional
```

## Requirements
- **For Docker:** Docker and Docker Compose
- **For Local:** Python 3.10+, LM Studio on port 1234
- **Always:** Telegram bot token

## Detailed Setup
See `docker/DOCKER.md` for comprehensive Docker instructions.

## Local Development Setup
1. Create and activate a virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Configure environment:
   ```bash
   cp .env.example .env
   # Edit .env with your tokens
   ```
4. Start LM Studio on port 1234 with your model
5. Run the bot:
   ```bash
   python bot.py
   ```
