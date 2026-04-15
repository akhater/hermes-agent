"""react_tool — let the agent set a Telegram message reaction.

The lifecycle reactions (👀 processing, 👍/👎 complete) are controlled by
``TELEGRAM_REACTIONS=1`` and are unchanged by this tool.  This tool is
governed by a *separate* flag — ``TELEGRAM_AGENT_REACTIONS=1`` — so the two
systems never race for the same message.

Config (config.yaml per-profile):
    telegram:
      reactions: true           # lifecycle reactions (👀/👍/👎) — existing
      agent_reactions: true     # enables this agent-callable tool
      signature_emoji: "❤"     # agent's default reaction; exposed in tool desc

Set TELEGRAM_REACTIONS=1 in env (or reactions: true in config) for lifecycle.
Set TELEGRAM_AGENT_REACTIONS=1 (or agent_reactions: true) for agent tool.
They are independent — you can enable either or both.
"""

import json
import logging
import os

logger = logging.getLogger(__name__)

# Telegram's reaction whitelist (non-premium subset that bots can always use).
# Full list: https://core.telegram.org/bots/api#reactiontypeemoji
ALLOWED_REACTIONS = {
    "👍", "👎", "❤", "🔥", "🥰", "👏", "😁", "🤔", "🤯", "😱",
    "🤬", "😢", "🎉", "🤩", "🤮", "💩", "🙏", "👌", "🕊", "🤡",
    "🥱", "🥴", "😍", "🐳", "❤‍🔥", "🌚", "🌭", "💯", "🤣", "⚡",
    "🍌", "🏆", "💔", "🤨", "😐", "🍓", "🍾", "💋", "🖕", "😈",
    "😴", "😭", "🤓", "👻", "👨‍💻", "👀", "🎃", "🙈", "😇", "😨",
    "🤝", "✍", "🤗", "🫡", "🎅", "🎄", "☃", "💅", "🤪", "🗿",
    "🆒", "💘", "🙉", "🦄", "😘", "💊", "🙊", "😎", "👾", "🤷",
    "😡",
}


def _agent_reactions_enabled() -> bool:
    return os.getenv("TELEGRAM_AGENT_REACTIONS", "false").lower() not in ("false", "0", "no")


def _signature_emoji() -> str:
    """Return this agent's configured signature emoji, or empty string."""
    return os.getenv("TELEGRAM_SIGNATURE_EMOJI", "").strip()


def _build_schema() -> dict:
    sig = _signature_emoji()
    sig_hint = f"  Your signature emoji is {sig} — use it as your default." if sig else ""
    return {
        "name": "react_to_message",
        "description": (
            "Add an emoji reaction to a Telegram message. "
            "Use sparingly and only when a reaction genuinely fits the moment — "
            "e.g. 🎉 for good news, ❤ for thanks, 🤔 when uncertain. "
            f"Requires TELEGRAM_AGENT_REACTIONS=1 and a Telegram session.{sig_hint}"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "message_id": {
                    "type": "string",
                    "description": "ID of the Telegram message to react to.",
                },
                "emoji": {
                    "type": "string",
                    "description": (
                        "Emoji from Telegram's reaction whitelist. "
                        "Common choices: 👍 👎 ❤ 🔥 🎉 🤔 😢 👀 🤩 🙏 💯 😎"
                        + (f"  Default: {sig}" if sig else "")
                    ),
                },
                "chat_id": {
                    "type": "string",
                    "description": (
                        "Telegram chat ID. Defaults to the current session chat — "
                        "omit unless reacting in a different chat."
                    ),
                },
            },
            "required": ["message_id", "emoji"],
        },
    }


def _check_react_tool() -> bool:
    """Only available in Telegram sessions with TELEGRAM_AGENT_REACTIONS=1."""
    if not _agent_reactions_enabled():
        return False
    from gateway.session_context import get_session_env
    return get_session_env("HERMES_SESSION_PLATFORM", "") == "telegram"


def react_tool(args, **kw):
    """Handle react_to_message tool calls."""
    if not _agent_reactions_enabled():
        return json.dumps({
            "error": "Agent reactions are disabled. Set TELEGRAM_AGENT_REACTIONS=1 to enable."
        })

    message_id = str(args.get("message_id", "")).strip()
    emoji = args.get("emoji", "").strip()

    if not message_id:
        return json.dumps({"error": "'message_id' is required."})

    # Fall back to signature emoji if caller omitted the emoji
    if not emoji:
        emoji = _signature_emoji()
    if not emoji:
        return json.dumps({"error": "'emoji' is required (or set TELEGRAM_SIGNATURE_EMOJI)."})

    # Warn but don't block on unknown emoji — Telegram will reject it with a
    # clear error, and the whitelist may lag behind API updates.
    if emoji not in ALLOWED_REACTIONS:
        logger.debug("[react_tool] emoji %r not in known whitelist; proceeding anyway", emoji)

    # Resolve chat_id: explicit arg → session context → error
    chat_id = str(args.get("chat_id", "")).strip()
    if not chat_id:
        from gateway.session_context import get_session_env
        chat_id = get_session_env("HERMES_SESSION_CHAT_ID", "")
    if not chat_id:
        return json.dumps({
            "error": "No chat_id available. Pass 'chat_id' explicitly or call from a Telegram session."
        })

    # Get bot token from gateway config
    try:
        from gateway.config import load_gateway_config, Platform
        config = load_gateway_config()
        pconfig = config.platforms.get(Platform.TELEGRAM)
        if not pconfig or not pconfig.enabled or not pconfig.token:
            return json.dumps({"error": "Telegram is not configured or has no token."})
        token = pconfig.token
    except Exception as e:
        return json.dumps({"error": f"Failed to load gateway config: {e}"})

    try:
        from model_tools import _run_async
        result = _run_async(_set_reaction(token, chat_id, message_id, emoji))
        return json.dumps(result)
    except Exception as e:
        return json.dumps({"error": f"react_to_message failed: {e}"})


async def _set_reaction(token: str, chat_id: str, message_id: str, emoji: str) -> dict:
    """Call Bot.set_message_reaction via python-telegram-bot."""
    try:
        from telegram import Bot
        bot = Bot(token=token)
        await bot.set_message_reaction(
            chat_id=int(chat_id),
            message_id=int(message_id),
            reaction=emoji,
        )
        return {"success": True, "chat_id": chat_id, "message_id": message_id, "emoji": emoji}
    except Exception as e:
        logger.debug("[react_tool] set_message_reaction failed (%s): %s", emoji, e)
        return {"error": f"Reaction failed: {e}"}


# Schema is built at import time so the tool description includes the
# signature emoji hint from the current environment.
REACT_SCHEMA = _build_schema()

# --- Registry ---
from tools.registry import registry

registry.register(
    name="react_to_message",
    toolset="messaging",
    schema=REACT_SCHEMA,
    handler=react_tool,
    check_fn=_check_react_tool,
    emoji="💬",
)
