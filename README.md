# Stas Chat

A Telegram bot that replies in the user's style using a local LM. The bot loads a persona from `persona.txt`, keeps a short conversation history per chat, and supports both LM Studio and containerized deployment.

## Features
- Style-preserving replies using a persona file
- Conversation history (limited to 20 messages by default)
- Two reply modes: `stylish` (short) and `detailed` (long)
- Simple media praise logic
- Commands: `/reset`, `/mode`, `/persona`, `/tone`, and `/addtogroup` for chat control
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
Standard development setup:

```bash
python -m venv .venv
source .venv/bin/activate  # macOS/Linux
pip install -r requirements.txt
python bot.py
```

## Project Structure
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

## Adding the bot to a group
Telegram bots cannot join a chat by opening a group invite link. A group administrator must add them.
Send `/addtogroup` to the bot to get Telegram's add-to-group link, then open it and select the target group.

## Replying from your own account (optional)
`userbot.py` is a separate Telegram client. It replies from your account, not from the bot account.
Create an application at [my.telegram.org](https://my.telegram.org), then add its credentials to `.env`:

```env
TELEGRAM_API_ID=123456
TELEGRAM_API_HASH=your_api_hash
USERBOT_SESSION=.userbot
GROUP_REPLY_CHANCE=0.01
```

Install dependencies and start it locally:

```bash
pip install -r requirements.txt
python3 userbot.py
```

On the first start Telegram will ask for your phone number and login code. The resulting `.userbot.session` file grants account access: keep it private and never commit or share it.

To toggle replies for one chat, send one of these messages from your account in that chat:

```text
/autorespond on
/autorespond off
/autorespond status
```

Set the reply tone for that chat with:

```text
/tone natural
/tone calm
/tone warm
/tone professional
/tone concise
/tone playful
/tone status
```

Choose the persona for that chat with:

```text
/persona classic
/persona personal
/persona example
/persona status
```

The command is deleted after it is handled and a confirmation is sent to Saved Messages. Auto-reply is stored per chat, including groups, so enable it only where automatic replies are appropriate.
Do not enable this mode in a private chat where the regular bot is also active, otherwise both accounts can reply to the same message.

In a private chat, auto-reply responds to every eligible text message. In groups it responds only to a random share of eligible messages; use `GROUP_REPLY_CHANCE` to set that share from `0` to `1` (for example, `0.05` means about 5%). Mentions of your Telegram username or the supported name variants (`Стас`, `Стасян`, `Сасян`, `СтасП`, and `Стас П`) always receive a reply.

The standard bot supports the same `/tone` and `/persona` values, stored in memory for the current chat until the bot restarts.

`persona.txt` is a generic example profile for testing. Personal and other reusable profiles are stored separately; the persona adapter combines the selected profile with the tone chosen for the chat.

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
