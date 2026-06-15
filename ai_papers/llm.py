"""LLM-based paper summarization using external APIs."""

import json
import logging
import os
from pathlib import Path
import re
import time
from typing import Optional

import requests


logger = logging.getLogger(__name__)

AI_FAIL_SUMMARY = "AI Fail"
_warned_messages: set[str] = set()
_provider_config_cache: dict[str, dict] = {}
_providers_order_cache: Optional[list[str]] = None


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _credentials_dir() -> Path:
    return _repo_root() / "user_credentials"


def _load_provider_config(provider: str) -> dict:
    """Load config for a specific provider, falling back to legacy credentials file."""
    try:
        from .config import load_config_file
        raw_config = load_config_file()
        if "llm" in raw_config and "providers" in raw_config["llm"] and provider in raw_config["llm"]["providers"]:
            return raw_config["llm"]["providers"][provider]
    except Exception:
        pass

    path = _credentials_dir() / f"{provider}_llm_config.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception as e:
        _warn_once(f"Failed to read {path.name}: {e}")
        return {}


def _load_providers_order() -> list[str]:
    """Load provider preference order, falling back to legacy providers file."""
    try:
        from .config import load_config_file
        raw_config = load_config_file()
        if "llm" in raw_config and "providers_order" in raw_config["llm"]:
            return raw_config["llm"]["providers_order"]
    except Exception:
        pass

    path = _credentials_dir() / "llm_providers.json"
    if not path.exists():
        return ["groq"]
    try:
        data = json.loads(path.read_text())
        return data.get("order", ["groq"])
    except Exception as e:
        _warn_once(f"Failed to read llm_providers.json: {e}")
        return ["groq"]


def get_default_provider() -> str:
    """Return the first provider in the preference order."""
    return _load_providers_order()[0]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _warn_once(message: str):
    """Log a warning only once per process."""
    if message not in _warned_messages:
        logger.warning(message)
        _warned_messages.add(message)


def _resolve_api_key(
    explicit_key: Optional[str], env_var_name: str, provider: str = ""
) -> Optional[str]:
    """Resolve API key: explicit → LLM_API_KEY env → provider env → provider config file."""
    if explicit_key:
        return explicit_key
    config = _load_provider_config(provider) if provider else {}
    alternate_env = "GEMINI_API_KEY" if env_var_name == "GOOGLE_API_KEY" else None
    return (
        os.environ.get("LLM_API_KEY")
        or os.environ.get(env_var_name)
        or (os.environ.get(alternate_env) if alternate_env else None)
        or config.get("api_key")
    )


def _get_provider_setting(provider: str, key: str, default=None):
    """Read an optional provider-specific setting from its config file."""
    return _load_provider_config(provider).get(key, default)


def _build_summary_prompt(title: str, abstract: str) -> str:
    """Build a concise prompt; abstract truncated to keep input tokens low."""
    truncated_abstract = abstract[:600] + ("..." if len(abstract) > 600 else "")
    return (
        f"Summarize this paper in 2-3 sentences covering: motivation, key findings, limitations.\n\n"
        f"Title: {title}\n"
        f"Abstract: {truncated_abstract}"
    )


def _clean_summary_text(text: Optional[str]) -> Optional[str]:
    """Strip common LLM boilerplate from summary responses."""
    if not text:
        return None

    cleaned = text.strip().strip('"').strip()

    # Common Groq/LLM lead-ins, including variants like "heres" and
    # misspelled "sentances".
    lead_in_patterns = [
        (
            r"^here'?s?\s+(?:a\s+)?summary\s+of\s+(?:the\s+)?paper"
            r"(?:\s+in\s+\d+(?:\s*-\s*\d+)?\s+sen(?:t|ta)ences)?"
            r"\s+covering\s+motivation,\s*key\s+findings(?:\s*,)?\s*(?:and\s+)?limitations:\s*"
        ),
        (
            r"^here\s+is\s+a\s+summary\s+of\s+(?:the\s+)?paper"
            r"(?:\s+in\s+\d+(?:\s*-\s*\d+)?\s+sen(?:t|ta)ences)?"
            r"\s+covering\s+motivation,\s*key\s+findings(?:\s*,)?\s*(?:and\s+)?limitations:\s*"
        ),
        r"^summary\s+of\s+(?:the\s+)?paper:\s*",
    ]

    for pattern in lead_in_patterns:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)

    # Fallback: remove any preamble variant up to the first colon when it
    # clearly matches the standard summary boilerplate intent.
    lowered = cleaned.lower()
    if (
        "summary of the paper" in lowered
        and "motivation" in lowered
        and "key findings" in lowered
        and "limitations" in lowered
        and ":" in cleaned
    ):
        cleaned = cleaned.split(":", 1)[1].strip()

    return cleaned.strip() or None


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def generate_summary(
    title: str,
    abstract: str,
    provider: Optional[str] = None,
    api_key: Optional[str] = None,
    retry: bool = True,
) -> str:
    """Generate an AI summary, falling back through providers on failure.

    Args:
        title: Paper title.
        abstract: Paper abstract.
        provider: Force a specific provider. If None, uses llm_providers.json order.
        api_key: Override API key (otherwise resolved from config/env).
        retry: Whether to retry with backoff on transient errors (e.g. 429).
               Set False for single on-demand GUI requests to return immediately.

    Returns:
        Summary text, or AI_FAIL_SUMMARY if all providers fail.
    """
    providers_to_try = [provider.lower()] if provider else _load_providers_order()

    for p in providers_to_try:
        func = _PROVIDER_FUNCS.get(p)
        if func is None:
            logger.error(f"Unknown LLM provider: {p}")
            continue

        kwargs: dict = {"api_key": api_key}
        if p == "google":
            kwargs["retry"] = retry

        result = func(title, abstract, **kwargs)
        if result:
            normalized = _clean_summary_text(result)
            return normalized or result.strip()

        if len(providers_to_try) > 1:
            logger.warning(f"Provider '{p}' failed, trying next provider...")

    return AI_FAIL_SUMMARY


# ---------------------------------------------------------------------------
# Provider implementations
# ---------------------------------------------------------------------------


def _summarize_groq(
    title: str, abstract: str, api_key: Optional[str] = None
) -> Optional[str]:
    """Summarize using Groq API (fast, generous free tier)."""
    try:
        from groq import Groq
    except ImportError:
        _warn_once("groq package not installed. Install with: pip install groq")
        return None

    api_key = _resolve_api_key(api_key, "GROQ_API_KEY", "groq")
    if not api_key:
        _warn_once(
            "No Groq API key found. Set GROQ_API_KEY, LLM_API_KEY, or groq_llm_config.json."
        )
        return None

    configured_model = _get_provider_setting("groq", "model")
    candidate_models = [
        model
        for model in [
            configured_model,
            "llama-3.1-8b-instant",
            "llama-3.3-70b-versatile",
        ]
        if model
    ]

    try:
        client = Groq(api_key=api_key)
        prompt = _build_summary_prompt(title, abstract)

        for model_name in candidate_models:
            try:
                message = client.chat.completions.create(
                    messages=[{"role": "user", "content": prompt}],
                    model=model_name,
                    max_tokens=150,
                    temperature=0.5,
                )
                return _clean_summary_text(message.choices[0].message.content)
            except Exception as error:
                logger.warning(f"Groq model '{model_name}' failed: {error}")

        logger.error("Groq API error: all candidate Groq models failed")
        return None
    except Exception as e:
        logger.error(f"Groq API error: {e}")
        return None


def _summarize_google(
    title: str, abstract: str, api_key: Optional[str] = None, retry: bool = True
) -> Optional[str]:
    """Summarize using Google Gemini via the REST API."""
    api_key = _resolve_api_key(api_key, "GOOGLE_API_KEY", "google")
    if not api_key:
        _warn_once(
            "No Google API key found. Set GOOGLE_API_KEY, LLM_API_KEY, or google_llm_config.json."
        )
        return None

    endpoint = (
        "https://generativelanguage.googleapis.com/v1beta/"
        f"models/gemini-2.0-flash:generateContent?key={api_key}"
    )
    payload = {
        "contents": [{"parts": [{"text": _build_summary_prompt(title, abstract)}]}],
        "generationConfig": {"temperature": 0.4, "maxOutputTokens": 150},
    }

    delays = (0, 2, 5, 10) if retry else (0,)
    for delay_seconds in delays:
        if delay_seconds:
            time.sleep(delay_seconds)
        try:
            response = requests.post(endpoint, json=payload, timeout=30)
            response.raise_for_status()
            data = response.json()
            candidates = data.get("candidates", [])
            if not candidates:
                logger.error("Google API error: no candidates returned")
                return None
            parts = candidates[0].get("content", {}).get("parts", [])
            text = "".join(part.get("text", "") for part in parts).strip()
            return _clean_summary_text(text)
        except requests.HTTPError as error:
            status_code = (
                error.response.status_code if error.response is not None else "unknown"
            )
            if status_code == 429 and retry and delay_seconds != 10:
                logger.warning(
                    "Google API rate limited (HTTP 429). Retrying after backoff."
                )
                continue
            logger.error(f"Google API error: HTTP {status_code}")
            return None
        except requests.RequestException as error:
            logger.error(f"Google API error: {error.__class__.__name__}")
            return None

    return None


def _summarize_openai(
    title: str, abstract: str, api_key: Optional[str] = None
) -> Optional[str]:
    """Summarize using OpenAI API."""
    try:
        from openai import OpenAI
    except ImportError:
        _warn_once("openai package not installed. Install with: pip install openai")
        return None

    api_key = _resolve_api_key(api_key, "OPENAI_API_KEY", "openai")
    if not api_key:
        _warn_once(
            "No OpenAI API key found. Set OPENAI_API_KEY, LLM_API_KEY, or openai_llm_config.json."
        )
        return None

    try:
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "user", "content": _build_summary_prompt(title, abstract)}
            ],
            max_tokens=150,
            temperature=0.5,
        )
        return _clean_summary_text(response.choices[0].message.content)
    except Exception as e:
        logger.error(f"OpenAI API error: {e}")
        return None


def _summarize_anthropic(
    title: str, abstract: str, api_key: Optional[str] = None
) -> Optional[str]:
    """Summarize using Anthropic Claude API."""
    try:
        import anthropic
    except ImportError:
        _warn_once(
            "anthropic package not installed. Install with: pip install anthropic"
        )
        return None

    api_key = _resolve_api_key(api_key, "ANTHROPIC_API_KEY", "anthropic")
    if not api_key:
        _warn_once(
            "No Anthropic API key found. Set ANTHROPIC_API_KEY, LLM_API_KEY, or anthropic_llm_config.json."
        )
        return None

    try:
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=150,
            messages=[
                {"role": "user", "content": _build_summary_prompt(title, abstract)}
            ],
        )
        return _clean_summary_text(message.content[0].text)
    except Exception as e:
        logger.error(f"Anthropic API error: {e}")
        return None


# Dispatch table — must be defined after the functions above
_PROVIDER_FUNCS = {
    "groq": _summarize_groq,
    "google": _summarize_google,
    "openai": _summarize_openai,
    "anthropic": _summarize_anthropic,
}
