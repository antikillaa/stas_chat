# Changelog

This file follows the [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format. The repository has no published releases, so entries are grouped by development date and milestone.

## [Unreleased]

### Changed

- In group chats, the userbot now replies to a random share of messages. Configure the share with `GROUP_REPLY_CHANCE` (1% by default).
- Direct mentions of the account by username or supported name variants now always receive a reply in group chats.
- The userbot now normalizes stored conversation history before sending it to the language model, preventing invalid role-order errors from strict prompt templates.

## [2026-09-04] — Account-based auto-reply

### Added

- A standalone `userbot.py` client that replies from an authenticated Telegram account through a local language model.
- `/autorespond on`, `/autorespond off`, and `/autorespond status` commands to manage auto-replies per chat.
- Persistent enabled-chat state and conversation history for reply generation.
- Authentication documentation for `TELEGRAM_API_ID` and `TELEGRAM_API_HASH`, including session-file safety.
- An `/addtogroup` command that provides Telegram's official link for adding the standard bot to a group.

## [2026-01-08] — Main bot and persona bot improvements

### Changed

- Improved the `bot.py` and `bot_anechka.py` message handlers, including group and mention handling.

## [2025-12-17] — Anechka bot

### Added

- A second Telegram bot, `bot_anechka.py`, with its own persona, moods, and Stasyan-message context.
- The `persona_ann.txt` persona file.

### Removed

- The obsolete `keep_alive.py` script.

## [2025-12-16] — Docker deployment

### Added

- A `Dockerfile` and Docker Compose configurations for local LM Studio and Ollama deployments.
- Detailed Docker setup instructions in `docker/DOCKER.md`.

### Changed

- Expanded the README with local and containerized model-run options.

## [2025-12-15] — Stable local workflow

### Changed

- Reworked `bot.py` for a working local LM Studio setup.
- Added the initial project README.
- Updated the main persona.

## [2025-12-09] — Service uptime support

### Added

- Experimental `keep_alive.py` support to prevent the service from sleeping.

## [2025-12-05] — Chat-mode restoration

### Changed

- Restored a working bot flow after webhook experiments.
- Temporarily removed media replies to focus on text chat.

## [2025-12-03] — LLM generation queue

### Changed

- Moved long-running LLM calls to a background queue to prevent webhook timeouts.
- Reworked webhook processing and temporarily silenced noisy webhook responses.

## [2025-12-02] — Media, groups, and runtime variants

### Added

- Photo and video reactions with a set of random phrases.
- Group-chat awareness for media handling.
- `keep_alive.py`, polling, and pre-start webhook removal in various development iterations.

### Changed

- Iterated on generation logic, imports, and the FastAPI/webhook integration.
- Restored reply generation after merge conflicts.

## [2025-11-27 — 2025-11-28] — Project foundation

### Added

- The initial Telegram bot with a persona, dependencies, and a Procfile worker.
- Early FastAPI, webhook, and aiohttp architecture integrations.

### Changed

- Fixed reply generation and refined the bot persona several times.
