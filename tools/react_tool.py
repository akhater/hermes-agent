"""react_tool — agent-callable Telegram reactions + signature emoji management.

The lifecycle reactions (👀 processing, 👍/👎 complete) are controlled by
``TELEGRAM_REACTIONS=1`` and are unchanged by this tool.  This tool is
governed by a *separate* flag — ``TELEGRAM_AGENT_REACTIONS=1`` — so the two
systems never race for the same message.

Config (config.yaml per-profile):
    telegram:
      reactions: true           # lifecycle reactions (👀/👍/👎) — existing
      agent_reactions: true     # enables this agent-callable tool
      signature_emoji: "💫"     # agent's default / identity reaction

Set TELEGRAM_REACTIONS=1 in env (or reactions: true in config) for lifecycle.
Set TELEGRAM_AGENT_REACTIONS=1 (or agent_reactions: true) for agent tool.
They are independent — you can enable either or both.

Actions:
  react          — set an emoji reaction on a message (default)
  set_signature  — persistently update this agent's signature emoji
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
    "😡", "🌟",
}


def _agent_reactions_enabled() -> bool:
    """Return True if TELEGRAM_AGENT_REACTIONS is set, or config.yaml enables it."""
    env_val = os.getenv("TELEGRAM_AGENT_REACTIONS", "").lower()
    if env_val:
        return env_val not in ("false", "0", "no")
    # Fallback: read directly from the profile's config.yaml (for cases where
    # load_gateway_config() hasn't run yet or the env var wasn't propagated).
    try:
        import yaml
        from hermes_constants import get_hermes_home
        cfg_path = get_hermes_home() / "config.yaml"
        if cfg_path.exists():
            with open(cfg_path, encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
            val = cfg.get("telegram", {}).get("agent_reactions", False)
            return bool(val) and str(val).lower() not in ("false", "0", "no")
    except Exception:
        pass
    return False


def _signature_emoji() -> str:
    """Return this agent's configured signature emoji, or empty string.

    Resolution order:
    1. TELEGRAM_SIGNATURE_EMOJI env var (set by load_gateway_config())
    2. config.yaml telegram.signature_emoji (direct read, timing-safe fallback)
    """
    val = os.getenv("TELEGRAM_SIGNATURE_EMOJI", "").strip()
    if val:
        return val
    try:
        import yaml
        from hermes_constants import get_hermes_home
        cfg_path = get_hermes_home() / "config.yaml"
        if cfg_path.exists():
            with open(cfg_path, encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
            return str(cfg.get("telegram", {}).get("signature_emoji", "")).strip()
    except Exception:
        pass
    return ""


def _build_schema() -> dict:
    sig = _signature_emoji()
    sig_hint = f"  Your signature emoji is {sig} — use it as your default." if sig else ""
    return {
        "name": "react_to_message",
        "description": (
            "Add an emoji reaction to a Telegram message, or change your signature emoji.\n\n"
            "USAGE — always pass emoji explicitly:\n"
            "  react_to_message(emoji=\"🔥\")           — react to the current message\n"
            "  react_to_message(emoji=\"🎉\", message_id=\"123\")  — react to a specific message\n"
            "  react_to_message(action=\"set_signature\", emoji=\"🌚\")  — change your default emoji\n\n"
            "Use reactions when a reaction genuinely fits: 🎉 good news, ❤ thanks, 🤔 uncertain, 🔥 exciting."
            + (f"\nYour signature emoji is {sig} — use it when you have no specific preference." if sig else "")
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["react", "set_signature"],
                    "description": (
                        "'react' (default) — set an emoji reaction on a message. "
                        "'set_signature' — persistently change your signature emoji "
                        "(saved to config.yaml and effective immediately)."
                    ),
                },
                "message_id": {
                    "type": "string",
                    "description": (
                        "ID of the Telegram message to react to. "
                        "Defaults to the current incoming message — omit to react to the message you're replying to."
                    ),
                },
                "emoji": {
                    "type": "string",
                    "description": (
                        "The emoji character to react with. "
                        "Confirmed working: 👍 👎 ❤ 🔥 🥰 👏 😁 🤔 🤯 😱 🤬 😢 🎉 🤩 💩 🙏 👌 🕊 🤡 🥱 "
                        "😍 🐳 🌚 🌟 💯 🤣 ⚡ 🍌 🏆 💔 😐 🍓 🍾 🖕 😈 😴 😭 🤓 👻 👨‍💻 👀 🎃 🙈 😇 "
                        "😨 🤝 🤗 🫡 💅 🤪 🗿 🆒 💘 🦄 😘 💊 😎 👾 🤷 😡"
                        + (f"  Your signature: {sig}" if sig else "")
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
            "required": ["emoji"],
        },
    }


def _check_react_tool() -> bool:
    """Only available in Telegram sessions with TELEGRAM_AGENT_REACTIONS=1.

    Uses the same fallback pattern as send_message: if session context isn't
    set yet (tool list built before session starts), fall back to checking
    whether Telegram is configured and running.
    """
    if not _agent_reactions_enabled():
        return False
    from gateway.session_context import get_session_env
    platform = get_session_env("HERMES_SESSION_PLATFORM", "")
    if platform:
        return platform == "telegram"
    # Fallback: session context not set yet — available if gateway is running
    # (same pattern as send_message check_fn)
    try:
        from gateway.status import is_gateway_running
        return is_gateway_running()
    except Exception:
        return False


def react_tool(args, **kw):
    """Handle react_to_message tool calls."""
    logger.info("[react_tool] called with args=%r", args)
    if not _agent_reactions_enabled():
        return json.dumps({
            "error": "Agent reactions are disabled. Set TELEGRAM_AGENT_REACTIONS=1 to enable."
        })

    action = args.get("action", "react")
    emoji = args.get("emoji", "").strip()

    if not emoji:
        emoji = _signature_emoji()
    if not emoji:
        return json.dumps({"error": "'emoji' is required (or set TELEGRAM_SIGNATURE_EMOJI)."})

    if emoji not in ALLOWED_REACTIONS:
        logger.debug("[react_tool] emoji %r not in known whitelist; attempting anyway", emoji)

    if action == "set_signature":
        return _handle_set_signature(emoji)

    # action == "react"
    message_id = str(args.get("message_id", "")).strip()
    if not message_id:
        from gateway.session_context import get_session_env
        message_id = get_session_env("HERMES_SESSION_MESSAGE_ID", "")
    if not message_id:
        return json.dumps({"error": "'message_id' is required for action='react'."})

    chat_id = str(args.get("chat_id", "")).strip()
    if not chat_id:
        from gateway.session_context import get_session_env
        chat_id = get_session_env("HERMES_SESSION_CHAT_ID", "")
    if not chat_id:
        return json.dumps({
            "error": "No chat_id available. Pass 'chat_id' explicitly or call from a Telegram session."
        })

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
        logger.info("[react_tool] setting reaction chat=%s msg=%s emoji=%r", chat_id, message_id, emoji)
        from model_tools import _run_async
        result = _run_async(_set_reaction(token, chat_id, message_id, emoji))
        logger.info("[react_tool] result: %r", result)
        return json.dumps(result)
    except Exception as e:
        return json.dumps({"error": f"react_to_message failed: {e}"})


def _handle_set_signature(emoji: str) -> str:
    """Persist a new signature emoji to config.yaml and update the running env."""
    try:
        from hermes_constants import get_hermes_home
        import yaml
        from utils import atomic_yaml_write

        config_path = get_hermes_home() / "config.yaml"

        user_config: dict = {}
        if config_path.exists():
            with open(config_path, encoding="utf-8") as f:
                user_config = yaml.safe_load(f) or {}

        if not isinstance(user_config.get("telegram"), dict):
            user_config["telegram"] = {}
        user_config["telegram"]["signature_emoji"] = emoji

        atomic_yaml_write(config_path, user_config, sort_keys=False)

        # Immediate effect in the running process
        os.environ["TELEGRAM_SIGNATURE_EMOJI"] = emoji

        return json.dumps({
            "success": True,
            "signature_emoji": emoji,
            "note": "Saved to config.yaml — effective immediately and on next restart.",
        })
    except Exception as e:
        return json.dumps({"error": f"set_signature failed: {e}"})


async def _set_reaction(token: str, chat_id: str, message_id: str, emoji: str) -> dict:
    """Call Bot.set_message_reaction via python-telegram-bot."""
    try:
        from telegram import Bot, ReactionTypeEmoji
        bot = Bot(token=token)
        await bot.set_message_reaction(
            chat_id=int(chat_id),
            message_id=int(message_id),
            reaction=[ReactionTypeEmoji(emoji=emoji)],
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
