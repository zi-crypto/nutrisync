"""
PostHog server-side analytics service for NutriSync.

Captures backend events that are invisible to the frontend JS SDK:
- AI tool invocations (which tools the LLM chooses, latency)
- Chat processing metrics (context loading time, token usage proxy)
- API endpoint usage patterns
- Workout plan generation, exercise logging, PR detection

Configuration:
    Set POSTHOG_API_KEY in your .env file (same project API key as frontend).
    Optionally set POSTHOG_HOST (defaults to https://eu.i.posthog.com).
"""

import logging
import os
from typing import Optional

from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# ── PostHog Client Singleton ─────────────────────────────────────────────────
_posthog_client = None


def _get_client():
    """Lazily initialize the PostHog client."""
    global _posthog_client
    if _posthog_client is not None:
        return _posthog_client

    api_key = os.getenv("POSTHOG_API_KEY", "")
    if not api_key:
        logger.warning("POSTHOG_API_KEY not set — server-side analytics disabled.")
        return None

    try:
        from posthog import Posthog

        host = os.getenv("POSTHOG_HOST", "https://eu.i.posthog.com")
        _posthog_client = Posthog(
            api_key=api_key,
            host=host,
            debug=os.getenv("POSTHOG_DEBUG", "false").lower() == "true",
            on_error=lambda e, items: logger.error(f"PostHog error: {e}"),
        )
        # Disable default geoip for server-side (the frontend handles this)
        _posthog_client.disabled = False
        logger.info(f"PostHog server-side analytics initialized (host={host})")
    except ImportError:
        logger.warning("posthog package not installed — server-side analytics disabled.")
    except Exception as e:
        logger.error(f"Failed to initialize PostHog: {e}")

    return _posthog_client


def capture(
    user_id: str,
    event: str,
    properties: Optional[dict] = None,
):
    """
    Capture a server-side event in PostHog.

    Args:
        user_id: The Supabase user UUID (distinct_id).
        event: Event name, e.g. 'api_chat_processed'.
        properties: Optional dict of event properties.
    """
    client = _get_client()
    if client is None:
        return

    try:
        client.capture(
            distinct_id=user_id,
            event=event,
            properties=properties or {},
        )
    except Exception as e:
        # Never let analytics break the app
        logger.error(f"PostHog capture failed: {e}")


def identify(
    user_id: str,
    properties: Optional[dict] = None,
):
    """
    Identify/update a user's properties in PostHog (server-side).

    Args:
        user_id: The Supabase user UUID.
        properties: Person properties to set (name, goal, etc.).
    """
    client = _get_client()
    if client is None:
        return

    try:
        client.identify(
            distinct_id=user_id,
            properties=properties or {},
        )
    except Exception as e:
        logger.error(f"PostHog identify failed: {e}")


def shutdown():
    """Flush pending events and shut down the PostHog client."""
    client = _get_client()
    if client is not None:
        try:
            client.shutdown()
        except Exception as e:
            logger.error(f"PostHog shutdown failed: {e}")
