# Stas Chat

A Telegram bot that replies in the user's style using a local LM (LM Studio). The bot loads a persona from `persona.txt`, keeps a short conversation history per chat, and uses a local OpenAI-compatible API at `http://127.0.0.1:1234/v1`.

## Features
- Style-preserving replies using a persona file.
- Conversation history (limited to 20 messages by default).
- Two reply modes: `stylish` (short) and `detailed` (long).
- Simple media praise logic.
- Commands: `\`/reset\`` and `\`/mode\`` for chat control.

## Requirements
- Python 3.10+
- `pip` and virtualenv (recommended)
- LM Studio (or other OpenAI-compatible server) running locally on port `1234`
- Telegram bot token

## Files
- `bot.py` — main bot implementation.
- `persona.txt` — persona text used to emulate your style.
- `.env` — environment variables (see below).
- `requirements.txt` — Python dependencies (create if missing).

## Environment (`.env`)
Create a file named `./.env` with the following variables:

TG_TOKEN=<your Telegram Bot Token>  
HF_TOKEN=<required token or placeholder>

Note: `HF_TOKEN` is validated by the bot but not actively used in the local LM Studio setup. Keep both set to avoid startup errors.

## LM Studio
LM Studio or a compatible OpenAI-like server must be running locally and reachable at:

http://127.0.0.1:1234/v1

The bot uses that endpoint via the OpenAI-compatible client.

## Installation
1. Create and activate a virtual environment:
   - macOS:
     ```bash
     python -m venv .venv
     source .venv/bin/activate
     ```
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
