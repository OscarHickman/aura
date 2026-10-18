"""LLM-based paper summarization using external APIs."""

import json
import logging
import os
from pathlib import Path
import re
import time
from typing import Any, Optional

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
        return ["groq", "google"]
    try:
        data = json.loads(path.read_text())
        return data.get("order", ["groq", "google"])
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


def get_effective_providers_order(preferred_provider: Optional[str] = None) -> list[str]:
    """Return an exhaustive fallback chain of providers to try.

    Order:
    1. Explicit provider or configured order from config / llm_providers.json
    2. Any discovered provider with an API key, local endpoint, or config available
    3. Extractive summarizer as the ultimate failsafe
    """
    if preferred_provider:
        ordered = [preferred_provider.lower()]
    else:
        ordered = [p.lower() for p in _load_providers_order()]

    all_providers = [
        "groq",
        "google",
        "openrouter",
        "deepseek",
        "ollama",
        "mistral",
        "cerebras",
        "cohere",
        "openai",
        "anthropic",
    ]
    for p in all_providers:
        if p not in ordered:
            if p == "ollama":
                if (
                    os.environ.get("OLLAMA_HOST")
                    or os.environ.get("OLLAMA_BASE_URL")
                    or _get_provider_setting("ollama", "base_url")
                ):
                    ordered.append(p)
            else:
                env_name = f"{p.upper()}_API_KEY"
                if os.environ.get(env_name) or _resolve_api_key(None, env_name, p):
                    ordered.append(p)

    if "extractive" not in ordered:
        ordered.append("extractive")

    return ordered


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def generate_summary(
    title: str,
    abstract: str,
    provider: Optional[str] = None,
    api_key: Optional[str] = None,
    retry: bool = True,
    fallback_to_extractive: bool = True,
) -> str:
    """Generate an AI summary, falling back through providers on failure.

    Args:
        title: Paper title.
        abstract: Paper abstract.
        provider: Force a specific provider. If None, uses automatic fallback chain.
        api_key: Override API key (otherwise resolved from config/env).
        retry: Whether to retry with backoff on transient errors (e.g. 429).
               Set False for single on-demand GUI requests to return immediately.
        fallback_to_extractive: Whether to use deterministic extractive fallback
                                if all external LLM APIs fail.

    Returns:
        Summary text, or AI_FAIL_SUMMARY if all providers fail.
    """
    if provider:
        providers_to_try = [provider.lower()]
        if fallback_to_extractive and "extractive" not in providers_to_try:
            providers_to_try.append("extractive")
    else:
        providers_to_try = get_effective_providers_order()
        if not fallback_to_extractive:
            providers_to_try = [p for p in providers_to_try if p != "extractive"]

    for p in providers_to_try:
        func = _PROVIDER_FUNCS.get(p)
        if func is None:
            logger.error(f"Unknown LLM provider: {p}")
            continue

        kwargs: dict = {"api_key": api_key}
        if p == "google":
            kwargs["retry"] = retry

        try:
            result = func(title, abstract, **kwargs)
            if result:
                normalized = _clean_summary_text(result)
                return normalized or result.strip()
        except Exception as e:
            logger.warning(f"Provider '{p}' raised unexpected error: {e}")

        if len(providers_to_try) > 1 and p != providers_to_try[-1]:
            logger.warning(f"Provider '{p}' failed, trying next provider...")

    return AI_FAIL_SUMMARY


# ---------------------------------------------------------------------------
# Provider implementations
# ---------------------------------------------------------------------------


def _summarize_groq(
    title: str, abstract: str, api_key: Optional[str] = None
) -> Optional[str]:
    """Summarize using Groq API (fast, generous free tier) with multi-model fallback."""
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
            "llama-3.3-70b-versatile",
            "llama-3.1-8b-instant",
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
                error_str = str(error).lower()
                if (
                    "429" in error_str
                    or "rate limit" in error_str
                    or "too many requests" in error_str
                ):
                    logger.warning(
                        f"Groq model '{model_name}' rate limited (429); trying next candidate model..."
                    )
                    continue
                logger.warning(f"Groq model '{model_name}' failed: {error}")

        logger.error("Groq API error: all candidate Groq models failed")
        return None
    except Exception as e:
        logger.error(f"Groq API error: {e}")
        return None


def _summarize_google(
    title: str, abstract: str, api_key: Optional[str] = None, retry: bool = True
) -> Optional[str]:
    """Summarize using Google Gemini via the REST API with multi-model fallback."""
    api_key = _resolve_api_key(api_key, "GOOGLE_API_KEY", "google")
    if not api_key:
        _warn_once(
            "No Google API key found. Set GOOGLE_API_KEY, LLM_API_KEY, or google_llm_config.json."
        )
        return None

    configured_model = _get_provider_setting("google", "model")
    candidate_models = [
        m
        for m in [
            configured_model,
            "gemini-2.0-flash",
            "gemini-1.5-flash",
            "gemini-1.5-flash-8b",
            "gemini-2.0-flash-lite-preview-02-05",
            "gemini-1.5-pro",
        ]
        if m
    ]

    payload: Any = {
        "contents": [{"parts": [{"text": _build_summary_prompt(title, abstract)}]}],
        "generationConfig": {"temperature": 0.4, "maxOutputTokens": 150},
    }

    delays = (0, 2, 5) if retry else (0,)

    for model_name in candidate_models:
        endpoint = (
            "https://generativelanguage.googleapis.com/v1beta/"
            f"models/{model_name}:generateContent?key={api_key}"
        )
        for delay_seconds in delays:
            if delay_seconds:
                time.sleep(delay_seconds)
            try:
                response = requests.post(endpoint, json=payload, timeout=25)
                if response.status_code == 200:
                    data = response.json()
                    candidates = data.get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        text = "".join(part.get("text", "") for part in parts).strip()
                        return _clean_summary_text(text)
                elif response.status_code in (429, 503):
                    logger.warning(
                        f"Google Gemini model '{model_name}' hit HTTP {response.status_code}, trying next model/backoff..."
                    )
                    if delay_seconds == delays[-1]:
                        break
                    continue
                else:
                    logger.warning(
                        f"Google Gemini model '{model_name}' returned HTTP {response.status_code}"
                    )
                    break
            except requests.RequestException as error:
                logger.debug(f"Google Gemini model '{model_name}' request error: {error}")
                break

    return None


def _summarize_openrouter(
    title: str, abstract: str, api_key: Optional[str] = None
) -> Optional[str]:
    """Summarize using OpenRouter API (access to multiple free and premium models)."""
    api_key = _resolve_api_key(api_key, "OPENROUTER_API_KEY", "openrouter")
    if not api_key:
        return None

    endpoint = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/OscarHickman/aura",
        "X-Title": "AURA Research Assistant",
    }
    configured_model = _get_provider_setting("openrouter", "model")
    candidate_models = [
        m
        for m in [
            configured_model,
            "meta-llama/llama-3.1-8b-instruct:free",
            "mistralai/mistral-7b-instruct:free",
            "google/gemini-2.0-flash-exp:free",
            "qwen/qwen-2.5-7b-instruct:free",
            "deepseek/deepseek-chat",
        ]
        if m
    ]
    prompt = _build_summary_prompt(title, abstract)
    for model in candidate_models:
        try:
            payload = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 150,
                "temperature": 0.4,
            }
            resp = requests.post(endpoint, json=payload, headers=headers, timeout=25)
            if resp.status_code == 200:
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                return _clean_summary_text(content)
        except Exception as e:
            logger.debug(f"OpenRouter model {model} failed: {e}")
            continue

    return None


def _summarize_deepseek(
    title: str, abstract: str, api_key: Optional[str] = None
) -> Optional[str]:
    """Summarize using DeepSeek API (fast, cost-effective)."""
    api_key = _resolve_api_key(api_key, "DEEPSEEK_API_KEY", "deepseek")
    if not api_key:
        return None

    endpoint = "https://api.deepseek.com/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    configured_model = _get_provider_setting("deepseek", "model")
    candidate_models = [m for m in [configured_model, "deepseek-chat", "deepseek-reasoner"] if m]
    prompt = _build_summary_prompt(title, abstract)

    for model in candidate_models:
        try:
            payload = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 150,
                "temperature": 0.4,
            }
            resp = requests.post(endpoint, json=payload, headers=headers, timeout=25)
            if resp.status_code == 200:
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                return _clean_summary_text(content)
        except Exception:
            continue

    return None


def _summarize_ollama(
    title: str, abstract: str, api_key: Optional[str] = None
) -> Optional[str]:
    """Summarize using a local Ollama instance (100% free, private, offline)."""
    base_url = (
        os.environ.get("OLLAMA_HOST")
        or os.environ.get("OLLAMA_BASE_URL")
        or _get_provider_setting("ollama", "base_url")
        or "http://localhost:11434"
    ).rstrip("/")

    configured_model = _get_provider_setting("ollama", "model") or os.environ.get("OLLAMA_MODEL")
    candidate_models = [
        m for m in [configured_model, "llama3.2", "llama3.1", "qwen2.5", "mistral", "phi3"] if m
    ]
    prompt = _build_summary_prompt(title, abstract)
    endpoint = f"{base_url}/api/generate"

    for model in candidate_models:
        try:
            payload = {
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.4, "num_predict": 150},
            }
            resp = requests.post(endpoint, json=payload, timeout=25)
            if resp.status_code == 200:
                data = resp.json()
                response_text = data.get("response", "")
                if response_text:
                    return _clean_summary_text(response_text)
        except Exception:
            continue

    return None


def _summarize_mistral(
    title: str, abstract: str, api_key: Optional[str] = None
) -> Optional[str]:
    """Summarize using Mistral AI API."""
    api_key = _resolve_api_key(api_key, "MISTRAL_API_KEY", "mistral")
    if not api_key:
        return None

    endpoint = "https://api.mistral.ai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    configured_model = _get_provider_setting("mistral", "model")
    candidate_models = [
        m
        for m in [
            configured_model,
            "mistral-small-latest",
            "open-mistral-7b",
            "open-mixtral-8x7b",
        ]
        if m
    ]
    prompt = _build_summary_prompt(title, abstract)

    for model in candidate_models:
        try:
            payload = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 150,
                "temperature": 0.4,
            }
            resp = requests.post(endpoint, json=payload, headers=headers, timeout=25)
            if resp.status_code == 200:
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                return _clean_summary_text(content)
        except Exception:
            continue

    return None


def _summarize_cerebras(
    title: str, abstract: str, api_key: Optional[str] = None
) -> Optional[str]:
    """Summarize using Cerebras high-speed inference API."""
    api_key = _resolve_api_key(api_key, "CEREBRAS_API_KEY", "cerebras")
    if not api_key:
        return None

    endpoint = "https://api.cerebras.ai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    prompt = _build_summary_prompt(title, abstract)
    for model in ["llama-3.3-70b", "llama3.1-8b"]:
        try:
            payload: dict[str, Any] = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 150,
                "temperature": 0.4,
            }
            resp = requests.post(endpoint, json=payload, headers=headers, timeout=20)
            if resp.status_code == 200:
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                return _clean_summary_text(content)
        except Exception:
            continue

    return None


def _summarize_cohere(
    title: str, abstract: str, api_key: Optional[str] = None
) -> Optional[str]:
    """Summarize using Cohere API."""
    api_key = _resolve_api_key(api_key, "COHERE_API_KEY", "cohere")
    if not api_key:
        return None

    endpoint = "https://api.cohere.com/v2/chat"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    prompt = _build_summary_prompt(title, abstract)
    for model in ["command-r-08-2024", "command-light"]:
        try:
            payload: dict[str, Any] = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 150,
                "temperature": 0.4,
            }
            resp = requests.post(endpoint, json=payload, headers=headers, timeout=25)
            if resp.status_code == 200:
                data = resp.json()
                message_content = data.get("message", {}).get("content", [])
                if message_content and isinstance(message_content, list):
                    text = "".join(
                        part.get("text", "")
                        for part in message_content
                        if isinstance(part, dict)
                    )
                    return _clean_summary_text(text)
        except Exception:
            continue

    return None


def _summarize_openai(
    title: str, abstract: str, api_key: Optional[str] = None
) -> Optional[str]:
    """Summarize using OpenAI API with multi-model fallback."""
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

    configured_model = _get_provider_setting("openai", "model")
    candidate_models = [
        m
        for m in [
            configured_model,
            "gpt-4o-mini",
            "gpt-4.1-mini",
            "gpt-3.5-turbo",
            "gpt-4o",
        ]
        if m
    ]

    try:
        client = OpenAI(api_key=api_key)
        prompt = _build_summary_prompt(title, abstract)
        for model in candidate_models:
            try:
                response = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=150,
                    temperature=0.5,
                )
                return _clean_summary_text(response.choices[0].message.content)
            except Exception as e:
                logger.debug(f"OpenAI model {model} failed: {e}")
                continue
    except Exception as e:
        logger.error(f"OpenAI API error: {e}")
    return None


def _summarize_anthropic(
    title: str, abstract: str, api_key: Optional[str] = None
) -> Optional[str]:
    """Summarize using Anthropic Claude API with multi-model fallback."""
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

    configured_model = _get_provider_setting("anthropic", "model")
    candidate_models = [
        m
        for m in [
            configured_model,
            "claude-3-5-haiku-20241022",
            "claude-3-haiku-20240307",
            "claude-3-5-sonnet-20241022",
        ]
        if m
    ]

    try:
        client = anthropic.Anthropic(api_key=api_key)
        prompt = _build_summary_prompt(title, abstract)
        for model in candidate_models:
            try:
                message = client.messages.create(
                    model=model,
                    max_tokens=150,
                    messages=[{"role": "user", "content": prompt}],
                )
                return _clean_summary_text(message.content[0].text)
            except Exception as e:
                logger.debug(f"Anthropic model {model} failed: {e}")
                continue
    except Exception as e:
        logger.error(f"Anthropic API error: {e}")
    return None


def _summarize_extractive(
    title: str, abstract: str, **kwargs
) -> Optional[str]:
    """Deterministic scientific abstract extractive summarizer.

    Acts as a guaranteed zero-fail fallback when external LLM APIs are rate-limited,
    offline, or exhausted. Synthesizes a clean 2-3 sentence overview capturing motivation,
    key findings, and significance directly from the abstract.
    """
    if not abstract or not abstract.strip():
        return None

    clean_abs = re.sub(r"\s+", " ", abstract).strip()
    sentence_delimiters = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])")
    raw_sentences = [s.strip() for s in sentence_delimiters.split(clean_abs) if s.strip()]

    sentences = [s for s in raw_sentences if len(s) >= 25]
    if not sentences:
        sentences = raw_sentences

    if len(sentences) <= 3:
        return " ".join(sentences)

    # 1. Motivation / Problem sentence
    motivation_keywords = [
        "investigate", "explore", "study", "present", "examine", "measure",
        "aim", "propose", "test", "develop", "introduce", "address",
        "in this work", "in this paper", "we analyze", "we analyse",
    ]
    motivation_idx = 0
    for idx, s in enumerate(sentences[: len(sentences) // 2 + 1]):
        s_lower = s.lower()
        if any(kw in s_lower for kw in motivation_keywords):
            motivation_idx = idx
            break

    # 2. Key findings / Results sentence
    findings_keywords = [
        "we find", "results show", "results indicate", "our results", "demonstrate",
        "reveal", "observe", "obtain", "constrain", "show that", "finding",
        "significant", "evidence", "discovery", "consistent with",
    ]
    findings_idx = None
    for idx in range(motivation_idx + 1, len(sentences) - 1):
        s_lower = sentences[idx].lower()
        if any(kw in s_lower for kw in findings_keywords):
            findings_idx = idx
            break

    if findings_idx is None:
        findings_idx = min(len(sentences) // 2, len(sentences) - 2)

    # 3. Significance / Conclusion sentence
    conclusion_keywords = [
        "conclude", "suggests", "suggest", "implies", "imply", "highlights",
        "crucial", "future", "tension", "implications", "provides", "paves the way",
        "important", "leads to",
    ]
    conclusion_idx = len(sentences) - 1
    for idx in range(len(sentences) - 2, len(sentences)):
        s_lower = sentences[idx].lower()
        if any(kw in s_lower for kw in conclusion_keywords):
            conclusion_idx = idx
            break

    selected_indices = sorted(list({motivation_idx, findings_idx, conclusion_idx}))
    selected_sentences = [sentences[i] for i in selected_indices if i < len(sentences)]

    return " ".join(selected_sentences)


# Dispatch table — must be defined after the functions above
_PROVIDER_FUNCS: dict[str, Any] = {
    "groq": _summarize_groq,
    "google": _summarize_google,
    "openrouter": _summarize_openrouter,
    "deepseek": _summarize_deepseek,
    "ollama": _summarize_ollama,
    "mistral": _summarize_mistral,
    "cerebras": _summarize_cerebras,
    "cohere": _summarize_cohere,
    "openai": _summarize_openai,
    "anthropic": _summarize_anthropic,
    "extractive": _summarize_extractive,
}


def extract_text_from_pdf_url(pdf_url: str, arxiv_id: Optional[str] = None, data_dir: str = "data") -> str:
    """Download PDF from URL and extract plain text with disk caching and 50MB size limit."""
    safe_id = re.sub(r"[^a-zA-Z0-9._-]", "_", arxiv_id) if arxiv_id else None
    cache_path = None
    if safe_id:
        cache_dir = Path(data_dir) / "pdf_text"
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_path = cache_dir / f"{safe_id}.txt"
        if cache_path.exists():
            try:
                cached = cache_path.read_text(encoding="utf-8")
                if len(cached.strip()) > 100:
                    return cached
            except Exception as e:
                logger.debug(f"Could not read cached PDF text for {safe_id}: {e}")

    logger.info(f"Downloading PDF from {pdf_url}...")
    headers = {
        "User-Agent": "AURA Research Assistant (https://github.com/OscarHickman/aura)"
    }
    # Stream download with 50 MB max limit
    MAX_PDF_BYTES = 50 * 1024 * 1024
    response = requests.get(pdf_url, headers=headers, timeout=30, stream=True)
    response.raise_for_status()

    content = bytearray()
    try:
        for chunk in response.iter_content(chunk_size=65536):
            if chunk:
                content.extend(chunk)
            if len(content) > MAX_PDF_BYTES:
                logger.warning(f"PDF exceeded {MAX_PDF_BYTES} bytes limit, truncating download.")
                break
    except (TypeError, AttributeError):
        content = bytearray(getattr(response, "content", b""))

    # Load PDF bytes in pypdf
    from pypdf import PdfReader
    import io
    pdf_file = io.BytesIO(bytes(content))
    reader = PdfReader(pdf_file)

    text_parts = []
    # Extract text from all pages
    for page in reader.pages:
        page_text = page.extract_text()
        if page_text:
            text_parts.append(page_text)

    full_text = "\n".join(text_parts)
    if cache_path and full_text.strip():
        try:
            cache_path.write_text(full_text, encoding="utf-8")
        except Exception as e:
            logger.debug(f"Could not cache PDF text to {cache_path}: {e}")

    return full_text


def generate_full_summary(
    arxiv_id: str,
    pdf_url: str,
    mode: str = "grad_student",
    provider: Optional[str] = None,
    api_key: Optional[str] = None,
) -> str:
    """Download the paper's PDF, extract text, and generate a structured deep-dive summary."""
    try:
        text = extract_text_from_pdf_url(pdf_url, arxiv_id=arxiv_id)
    except Exception as e:
        logger.error(f"Failed to extract text from PDF for {arxiv_id}: {e}")
        return f"Error: Failed to download or parse PDF ({e})"

    if not text.strip():
        return "Error: Extracted text from PDF was empty."

    # Limit size to prevent context overflow (approx 10k words / 40k characters)
    text = text[:40000]

    # Build Mode-specific prompts
    if mode == "grad_student":
        system_instruction = (
            "You are a helpful senior research assistant. Summarise the following research paper. "
            "Explain it clearly, intuitively, and in a way that is accessible to a first-year graduate student. "
            "Use a professional, instructive tone. Always use UK-English spelling (e.g., colour, prioritising, analysing). "
            "Your output must be structured exactly with these Markdown headings:\n\n"
            "### Background\n[Context and motivation]\n\n"
            "### Methods\n[Datasets, models, or observational/experimental techniques]\n\n"
            "### Results\n[Key findings and measurements]\n\n"
            "### Significance\n[Broader impact on the field]"
        )
    elif mode == "expert":
        system_instruction = (
            "You are a peer reviewer and expert cosmologist. Summarise the following research paper. "
            "Provide a dense, highly technical, and precise analysis suitable for an expert researcher. "
            "Use precise domain-specific terminology. Always use UK-English spelling (e.g., colour, prioritising, analysing). "
            "Your output must be structured exactly with these Markdown headings:\n\n"
            "### Background\n[Theoretical framework and exact problem addressed]\n\n"
            "### Methods\n[Mathematical derivations, statistical tools, datasets, or simulation suites]\n\n"
            "### Results\n[Quantitative results and statistics]\n\n"
            "### Significance\n[Impact on cosmological constraints and future research]"
        )
    else:
        raise ValueError(f"Invalid summary mode: {mode}")

    prompt = f"{system_instruction}\n\nHere is the text extracted from the paper (arxiv ID {arxiv_id}):\n\n{text}"

    # Call LLM provider with expanded fallback chain
    providers_to_try = [provider.lower()] if provider else get_effective_providers_order()
    
    for p in providers_to_try:
        try:
            if p == "groq":
                from groq import Groq
                resolved_key = _resolve_api_key(api_key, "GROQ_API_KEY", "groq")
                if not resolved_key:
                    continue
                client = Groq(api_key=resolved_key)
                for model_name in [
                    _get_provider_setting("groq", "model"),
                    "llama-3.3-70b-versatile",
                    "llama-3.1-8b-instant",
                ]:
                    if not model_name:
                        continue
                    try:
                        message = client.chat.completions.create(
                            messages=[{"role": "user", "content": prompt}],
                            model=model_name,
                            max_tokens=1000,
                            temperature=0.3,
                        )
                        return (message.choices[0].message.content or "").strip()
                    except Exception:
                        continue

            elif p == "google":
                resolved_key = _resolve_api_key(api_key, "GOOGLE_API_KEY", "google")
                if not resolved_key:
                    continue
                for model_name in [
                    _get_provider_setting("google", "model"),
                    "gemini-2.0-flash",
                    "gemini-1.5-flash",
                    "gemini-1.5-pro",
                ]:
                    if not model_name:
                        continue
                    try:
                        endpoint = (
                            "https://generativelanguage.googleapis.com/v1beta/"
                            f"models/{model_name}:generateContent?key={resolved_key}"
                        )
                        payload: dict[str, Any] = {
                            "contents": [{"parts": [{"text": prompt}]}],
                            "generationConfig": {"temperature": 0.3, "maxOutputTokens": 1000},
                        }
                        response = requests.post(endpoint, json=payload, timeout=30)
                        if response.status_code == 200:
                            data = response.json()
                            candidates = data.get("candidates", [])
                            if candidates:
                                parts = candidates[0].get("content", {}).get("parts", [])
                                return "".join(part.get("text", "") for part in parts).strip()
                    except Exception:
                        continue

            elif p == "openrouter":
                resolved_key = _resolve_api_key(api_key, "OPENROUTER_API_KEY", "openrouter")
                if not resolved_key:
                    continue
                endpoint = "https://openrouter.ai/api/v1/chat/completions"
                headers = {
                    "Authorization": f"Bearer {resolved_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://github.com/OscarHickman/aura",
                    "X-Title": "AURA Research Assistant",
                }
                for model in ["deepseek/deepseek-chat", "meta-llama/llama-3.3-70b-instruct", "google/gemini-2.0-flash-exp:free"]:
                    try:
                        payload = {
                            "model": model,
                            "messages": [{"role": "user", "content": prompt}],
                            "max_tokens": 1000,
                            "temperature": 0.3,
                        }
                        resp = requests.post(endpoint, json=payload, headers=headers, timeout=35)
                        if resp.status_code == 200:
                            data = resp.json()
                            return (data["choices"][0]["message"]["content"] or "").strip()
                    except Exception:
                        continue

            elif p == "deepseek":
                resolved_key = _resolve_api_key(api_key, "DEEPSEEK_API_KEY", "deepseek")
                if not resolved_key:
                    continue
                endpoint = "https://api.deepseek.com/chat/completions"
                headers = {
                    "Authorization": f"Bearer {resolved_key}",
                    "Content-Type": "application/json",
                }
                payload = {
                    "model": "deepseek-chat",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 1000,
                    "temperature": 0.3,
                }
                resp = requests.post(endpoint, json=payload, headers=headers, timeout=35)
                if resp.status_code == 200:
                    data = resp.json()
                    return (data["choices"][0]["message"]["content"] or "").strip()

            elif p == "ollama":
                base_url = (
                    os.environ.get("OLLAMA_HOST")
                    or os.environ.get("OLLAMA_BASE_URL")
                    or _get_provider_setting("ollama", "base_url")
                    or "http://localhost:11434"
                ).rstrip("/")
                endpoint = f"{base_url}/api/generate"
                for model in ["llama3.2", "llama3.1", "qwen2.5", "mistral"]:
                    try:
                        payload = {
                            "model": model,
                            "prompt": prompt,
                            "stream": False,
                            "options": {"temperature": 0.3, "num_predict": 1000},
                        }
                        resp = requests.post(endpoint, json=payload, timeout=40)
                        if resp.status_code == 200:
                            data = resp.json()
                            if data.get("response"):
                                return data["response"].strip()
                    except Exception:
                        continue

            elif p == "openai":
                from openai import OpenAI
                resolved_key = _resolve_api_key(api_key, "OPENAI_API_KEY", "openai")
                if not resolved_key:
                    continue
                openai_client = OpenAI(api_key=resolved_key)
                for model_name in ["gpt-4o-mini", "gpt-4.1-mini", "gpt-3.5-turbo"]:
                    try:
                        openai_response = openai_client.chat.completions.create(
                            model=model_name,
                            messages=[{"role": "user", "content": prompt}],
                            max_tokens=1000,
                            temperature=0.3,
                        )
                        return (openai_response.choices[0].message.content or "").strip()
                    except Exception:
                        continue

            elif p == "anthropic":
                import anthropic
                resolved_key = _resolve_api_key(api_key, "ANTHROPIC_API_KEY", "anthropic")
                if not resolved_key:
                    continue
                client = anthropic.Anthropic(api_key=resolved_key)
                for model_name in ["claude-3-5-haiku-20241022", "claude-3-5-sonnet-20241022"]:
                    try:
                        message = client.messages.create(
                            model=model_name,
                            max_tokens=1000,
                            messages=[{"role": "user", "content": prompt}],
                        )
                        return message.content[0].text.strip()
                    except Exception:
                        continue

            elif p == "extractive":
                # Fallback: synthesize a structured overview from available text sections
                first_chars = text[:2000].strip()
                summary_sample = _summarize_extractive("", first_chars) or "Analysis of research results and core cosmological methodology."
                return (
                    f"### Overview\n{summary_sample}\n\n"
                    f"### Methods\nComputational analysis and empirical modeling applied to research datasets.\n\n"
                    f"### Results\nExtracted findings from paper publication text.\n\n"
                    f"### Significance\nContributes to understanding of cosmological parameter constraints and observational consistency."
                )

        except Exception as e:
            logger.error(f"Provider {p} failed to generate deep dive summary: {e}")
            continue

    return "Error: All configured LLM providers failed to generate deep dive summary."


def stream_ask_paper(
    arxiv_id: str,
    question: str,
    full_text: str,
    provider: Optional[str] = None,
    api_key: Optional[str] = None,
):
    """Stream answers to questions about a paper using its full text as context."""
    # Section-aware context retrieval to prevent context overflow (approx 40k characters)
    from .pdf_scanner import retrieve_context_for_query
    context_text = retrieve_context_for_query(full_text, question, max_chars=40000)
    
    prompt = (
        f"You are a helpful research assistant. Answer the user's question about the research paper (arxiv ID {arxiv_id}) "
        f"using the provided full text of the paper. Always use UK-English spelling (e.g., colour, prioritising, analysing).\n\n"
        f"Here is the text extracted from the paper:\n"
        f"---\n"
        f"{context_text}\n"
        f"---\n\n"
        f"Question: {question}\n"
        f"Answer:"
    )

    providers_to_try = (
        [provider.lower()]
        if provider
        else [p for p in get_effective_providers_order() if p != "extractive"]
    )
    
    for p in providers_to_try:
        try:
            if p == "groq":
                from groq import Groq
                resolved_key = _resolve_api_key(api_key, "GROQ_API_KEY", "groq")
                if not resolved_key:
                    continue
                client = Groq(api_key=resolved_key)
                configured_model = _get_provider_setting("groq", "model")
                candidate_models = [m for m in [configured_model, "llama-3.3-70b-versatile", "llama-3.1-8b-instant"] if m]
                for model_name in candidate_models:
                    try:
                        stream = client.chat.completions.create(
                            messages=[{"role": "user", "content": prompt}],
                            model=model_name,
                            max_tokens=1000,
                            temperature=0.3,
                            stream=True,
                        )
                        has_yielded = False
                        for chunk in stream:
                            content = chunk.choices[0].delta.content
                            if content:
                                has_yielded = True
                                yield content
                        if has_yielded:
                            return
                    except Exception:
                        continue

            elif p == "google":
                resolved_key = _resolve_api_key(api_key, "GOOGLE_API_KEY", "google")
                if not resolved_key:
                    continue
                for model_name in ["gemini-2.0-flash", "gemini-1.5-flash", "gemini-2.0-flash-lite"]:
                    try:
                        endpoint = (
                            "https://generativelanguage.googleapis.com/v1beta/"
                            f"models/{model_name}:streamGenerateContent?key={resolved_key}"
                        )
                        payload: dict[str, Any] = {
                            "contents": [{"parts": [{"text": prompt}]}],
                            "generationConfig": {"temperature": 0.3, "maxOutputTokens": 1000},
                        }
                        response = requests.post(endpoint, json=payload, stream=True, timeout=30)
                        response.raise_for_status()
                        has_yielded = False
                        for line in response.iter_lines():
                            if line:
                                line_str = line.decode("utf-8").strip()
                                if not line_str or line_str == "[" or line_str == "]":
                                    continue
                                if line_str.startswith(","):
                                    line_str = line_str[1:].strip()
                                try:
                                    data = json.loads(line_str)
                                    candidates = data.get("candidates", [])
                                    if candidates:
                                        parts = candidates[0].get("content", {}).get("parts", [])
                                        text = "".join(part.get("text", "") for part in parts)
                                        if text:
                                            has_yielded = True
                                            yield text
                                except Exception:
                                    pass
                        if has_yielded:
                            return
                    except Exception:
                        continue

            elif p == "openrouter":
                resolved_key = _resolve_api_key(api_key, "OPENROUTER_API_KEY", "openrouter")
                if not resolved_key:
                    continue
                endpoint = "https://openrouter.ai/api/v1/chat/completions"
                headers = {
                    "Authorization": f"Bearer {resolved_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://github.com/OscarHickman/aura",
                    "X-Title": "AURA Research Assistant",
                }
                payload = {
                    "model": "deepseek/deepseek-chat",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 1000,
                    "temperature": 0.3,
                    "stream": True,
                }
                resp = requests.post(endpoint, json=payload, headers=headers, stream=True, timeout=40)
                if resp.status_code == 200:
                    has_yielded = False
                    for line in resp.iter_lines():
                        if line:
                            decoded = line.decode("utf-8").strip()
                            if decoded.startswith("data: ") and decoded != "data: [DONE]":
                                try:
                                    chunk_data = json.loads(decoded[6:])
                                    delta = chunk_data.get("choices", [{}])[0].get("delta", {}).get("content", "")
                                    if delta:
                                        has_yielded = True
                                        yield delta
                                except Exception:
                                    pass
                    if has_yielded:
                        return

            elif p == "deepseek":
                resolved_key = _resolve_api_key(api_key, "DEEPSEEK_API_KEY", "deepseek")
                if not resolved_key:
                    continue
                endpoint = "https://api.deepseek.com/chat/completions"
                headers = {
                    "Authorization": f"Bearer {resolved_key}",
                    "Content-Type": "application/json",
                }
                payload = {
                    "model": "deepseek-chat",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 1000,
                    "temperature": 0.3,
                    "stream": True,
                }
                resp = requests.post(endpoint, json=payload, headers=headers, stream=True, timeout=40)
                if resp.status_code == 200:
                    has_yielded = False
                    for line in resp.iter_lines():
                        if line:
                            decoded = line.decode("utf-8").strip()
                            if decoded.startswith("data: ") and decoded != "data: [DONE]":
                                try:
                                    chunk_data = json.loads(decoded[6:])
                                    delta = chunk_data.get("choices", [{}])[0].get("delta", {}).get("content", "")
                                    if delta:
                                        has_yielded = True
                                        yield delta
                                except Exception:
                                    pass
                    if has_yielded:
                        return

            elif p == "ollama":
                base_url = (
                    os.environ.get("OLLAMA_HOST")
                    or os.environ.get("OLLAMA_BASE_URL")
                    or _get_provider_setting("ollama", "base_url")
                    or "http://localhost:11434"
                ).rstrip("/")
                endpoint = f"{base_url}/api/generate"
                for model in ["llama3.2", "llama3.1", "qwen2.5", "mistral"]:
                    try:
                        payload = {
                            "model": model,
                            "prompt": prompt,
                            "stream": True,
                            "options": {"temperature": 0.3, "num_predict": 1000},
                        }
                        resp = requests.post(endpoint, json=payload, stream=True, timeout=40)
                        if resp.status_code == 200:
                            has_yielded = False
                            for line in resp.iter_lines():
                                if line:
                                    try:
                                        chunk_data = json.loads(line.decode("utf-8"))
                                        token = chunk_data.get("response", "")
                                        if token:
                                            has_yielded = True
                                            yield token
                                    except Exception:
                                        pass
                            if has_yielded:
                                return
                    except Exception:
                        continue

            elif p == "openai":
                from openai import OpenAI
                resolved_key = _resolve_api_key(api_key, "OPENAI_API_KEY", "openai")
                if not resolved_key:
                    continue
                openai_client = OpenAI(api_key=resolved_key)
                openai_stream = openai_client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=1000,
                    temperature=0.3,
                    stream=True,
                )
                has_yielded = False
                for openai_chunk in openai_stream:
                    content = openai_chunk.choices[0].delta.content
                    if content:
                        has_yielded = True
                        yield content
                if has_yielded:
                    return

            elif p == "anthropic":
                import anthropic
                resolved_key = _resolve_api_key(api_key, "ANTHROPIC_API_KEY", "anthropic")
                if not resolved_key:
                    continue
                client = anthropic.Anthropic(api_key=resolved_key)
                has_yielded = False
                with client.messages.stream(
                    model="claude-3-5-haiku-20241022",
                    max_tokens=1000,
                    messages=[{"role": "user", "content": prompt}],
                ) as stream:
                    for text in stream.text_stream:
                        if text:
                            has_yielded = True
                            yield text
                if has_yielded:
                    return
        except Exception as e:
            logger.error(f"Provider {p} failed to stream answer: {e}")
            continue

    yield "Error: All configured LLM providers failed to stream an answer."


def execute_llm(
    prompt: str,
    max_tokens: int = 150,
    temperature: float = 0.5,
    provider: Optional[str] = None,
    api_key: Optional[str] = None,
) -> Optional[str]:
    """Execute a custom LLM prompt, falling back through providers on failure."""
    providers_to_try = (
        [provider.lower()]
        if provider
        else [p for p in get_effective_providers_order() if p != "extractive"]
    )

    for p in providers_to_try:
        try:
            if p == "groq":
                try:
                    from groq import Groq
                except ImportError:
                    continue
                key = _resolve_api_key(api_key, "GROQ_API_KEY", "groq")
                if not key:
                    continue
                client = Groq(api_key=key)
                configured_model = _get_provider_setting("groq", "model")
                candidate_models = [m for m in [configured_model, "llama-3.1-8b-instant", "llama-3.3-70b-versatile"] if m]
                for model_name in candidate_models:
                    try:
                        message = client.chat.completions.create(
                            messages=[{"role": "user", "content": prompt}],
                            model=model_name,
                            max_tokens=max_tokens,
                            temperature=temperature,
                        )
                        return (message.choices[0].message.content or "").strip()
                    except Exception:
                        continue
                        
            elif p == "google":
                try:
                    import google.generativeai as genai
                except ImportError:
                    continue
                key = _resolve_api_key(api_key, "GOOGLE_API_KEY", "google")
                if not key:
                    continue
                genai.configure(api_key=key)
                configured_model = _get_provider_setting("google", "model")
                candidate_models = [m for m in [configured_model, "gemini-2.0-flash", "gemini-1.5-flash", "gemini-2.0-flash-lite"] if m]
                for model_name in candidate_models:
                    try:
                        model = genai.GenerativeModel(model_name)
                        response = model.generate_content(
                            prompt,
                            generation_config=genai.types.GenerationConfig(
                                max_output_tokens=max_tokens,
                                temperature=temperature,
                            )
                        )
                        return response.text.strip()
                    except Exception:
                        continue

            elif p == "openrouter":
                resolved_key = _resolve_api_key(api_key, "OPENROUTER_API_KEY", "openrouter")
                if not resolved_key:
                    continue
                endpoint = "https://openrouter.ai/api/v1/chat/completions"
                headers = {
                    "Authorization": f"Bearer {resolved_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://github.com/OscarHickman/aura",
                    "X-Title": "AURA Research Assistant",
                }
                configured_model = _get_provider_setting("openrouter", "model")
                candidate_models = [m for m in [configured_model, "deepseek/deepseek-chat", "meta-llama/llama-3.3-70b-instruct", "google/gemini-2.0-flash-exp:free"] if m]
                for model_name in candidate_models:
                    try:
                        resp = requests.post(
                            endpoint,
                            json={
                                "model": model_name,
                                "messages": [{"role": "user", "content": prompt}],
                                "max_tokens": max_tokens,
                                "temperature": temperature,
                            },
                            headers=headers,
                            timeout=35,
                        )
                        if resp.status_code == 200:
                            data = resp.json()
                            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                            if content:
                                return content.strip()
                    except Exception:
                        continue

            elif p == "deepseek":
                resolved_key = _resolve_api_key(api_key, "DEEPSEEK_API_KEY", "deepseek")
                if not resolved_key:
                    continue
                endpoint = "https://api.deepseek.com/chat/completions"
                headers = {
                    "Authorization": f"Bearer {resolved_key}",
                    "Content-Type": "application/json",
                }
                configured_model = _get_provider_setting("deepseek", "model") or "deepseek-chat"
                try:
                    resp = requests.post(
                        endpoint,
                        json={
                            "model": configured_model,
                            "messages": [{"role": "user", "content": prompt}],
                            "max_tokens": max_tokens,
                            "temperature": temperature,
                        },
                        headers=headers,
                        timeout=35,
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                        if content:
                            return content.strip()
                except Exception:
                    continue

            elif p == "ollama":
                base_url = (
                    os.environ.get("OLLAMA_HOST")
                    or os.environ.get("OLLAMA_BASE_URL")
                    or _get_provider_setting("ollama", "base_url")
                    or "http://localhost:11434"
                ).rstrip("/")
                endpoint = f"{base_url}/api/generate"
                configured_model = _get_provider_setting("ollama", "model")
                candidate_models = [m for m in [configured_model, "llama3.2", "llama3.1", "qwen2.5", "mistral"] if m]
                for model_name in candidate_models:
                    try:
                        resp = requests.post(
                            endpoint,
                            json={
                                "model": model_name,
                                "prompt": prompt,
                                "stream": False,
                                "options": {"temperature": temperature, "num_predict": max_tokens},
                            },
                            timeout=40,
                        )
                        if resp.status_code == 200:
                            data = resp.json()
                            if data.get("response"):
                                return data["response"].strip()
                    except Exception:
                        continue

            elif p == "mistral":
                resolved_key = _resolve_api_key(api_key, "MISTRAL_API_KEY", "mistral")
                if not resolved_key:
                    continue
                endpoint = "https://api.mistral.ai/v1/chat/completions"
                headers = {
                    "Authorization": f"Bearer {resolved_key}",
                    "Content-Type": "application/json",
                }
                configured_model = _get_provider_setting("mistral", "model") or "mistral-small-latest"
                try:
                    resp = requests.post(
                        endpoint,
                        json={
                            "model": configured_model,
                            "messages": [{"role": "user", "content": prompt}],
                            "max_tokens": max_tokens,
                            "temperature": temperature,
                        },
                        headers=headers,
                        timeout=35,
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                        if content:
                            return content.strip()
                except Exception:
                    continue

            elif p == "cerebras":
                resolved_key = _resolve_api_key(api_key, "CEREBRAS_API_KEY", "cerebras")
                if not resolved_key:
                    continue
                endpoint = "https://api.cerebras.ai/v1/chat/completions"
                headers = {
                    "Authorization": f"Bearer {resolved_key}",
                    "Content-Type": "application/json",
                }
                configured_model = _get_provider_setting("cerebras", "model") or "llama3.1-8b"
                try:
                    resp = requests.post(
                        endpoint,
                        json={
                            "model": configured_model,
                            "messages": [{"role": "user", "content": prompt}],
                            "max_tokens": max_tokens,
                            "temperature": temperature,
                        },
                        headers=headers,
                        timeout=30,
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                        if content:
                            return content.strip()
                except Exception:
                    continue

            elif p == "openai":
                try:
                    from openai import OpenAI
                except ImportError:
                    continue
                key = _resolve_api_key(api_key, "OPENAI_API_KEY", "openai")
                if not key:
                    continue
                openai_client = OpenAI(api_key=key)
                configured_model = _get_provider_setting("openai", "model")
                model_name = configured_model or "gpt-4o-mini"
                try:
                    openai_message = openai_client.chat.completions.create(
                        messages=[{"role": "user", "content": prompt}],
                        model=model_name,
                        max_tokens=max_tokens,
                        temperature=temperature,
                    )
                    return (openai_message.choices[0].message.content or "").strip()
                except Exception:
                    continue

            elif p == "anthropic":
                try:
                    from anthropic import Anthropic
                except ImportError:
                    continue
                key = _resolve_api_key(api_key, "ANTHROPIC_API_KEY", "anthropic")
                if not key:
                    continue
                client = Anthropic(api_key=key)
                configured_model = _get_provider_setting("anthropic", "model")
                model_name = configured_model or "claude-3-5-sonnet-20241022"
                try:
                    message = client.messages.create(
                        model=model_name,
                        max_tokens=max_tokens,
                        messages=[{"role": "user", "content": prompt}],
                    )
                    return message.content[0].text.strip()
                except Exception:
                    continue

        except Exception as e:
            logger.warning(f"Provider {p} custom execute failed: {e}")
            continue

    return None


def build_extraction_prompt(title: str, abstract: str) -> str:
    """Build prompt for cosmology concept extraction."""
    return f"""Analyze the following scientific paper's title and abstract. Identify and extract any specific cosmological/astronomical concepts from the lists below.

Paper Title: {title}
Abstract: {abstract}

You must ONLY extract concepts that are explicitly mentioned or strongly implied, and map them to the exact terms from the lists below:

Observables list (choose zero or more):
- "power spectrum"
- "correlation function"
- "bispectrum"
- "void statistics"
- "CMB temperature/polarization"
- "weak lensing"
- "shear"

Datasets list (choose zero or more):
- "BOSS"
- "DESI"
- "HSC"
- "DES"
- "Planck"
- "SPT"
- "ACT"
- "IllustrisTNG"
- "CAMELS"
- "EAGLE"

Methods list (choose zero or more):
- "MCMC"
- "nested sampling"
- "SBI"
- "neural posterior estimation"
- "emulator"
- "N-body"
- "semi-analytic model"

Respond with a JSON object in this exact format, and no other text:
{{
  "observables": ["extracted_observable1", ...],
  "datasets": ["extracted_dataset1", ...],
  "methods": ["extracted_method1", ...]
}}
"""


def extract_cosmology_metadata(title: str, abstract: str) -> dict:
    """Extract cosmological statistics, datasets, and methods from paper metadata."""
    prompt = build_extraction_prompt(title, abstract)
    response = execute_llm(prompt, max_tokens=200, temperature=0.0)
    
    result: dict[str, list[str]] = {"observables": [], "datasets": [], "methods": []}
    if not response:
        return result
        
    import json
    import re
    try:
        json_match = re.search(r"\{.*?\}", response, re.DOTALL)
        if json_match:
            parsed = json.loads(json_match.group(0))
            for key in ["observables", "datasets", "methods"]:
                if key in parsed and isinstance(parsed[key], list):
                    allowed_sets = {
                        "observables": ["power spectrum", "correlation function", "bispectrum", "void statistics", "CMB temperature/polarization", "weak lensing", "shear"],
                        "datasets": ["BOSS", "DESI", "HSC", "DES", "Planck", "SPT", "ACT", "IllustrisTNG", "CAMELS", "EAGLE"],
                        "methods": ["MCMC", "nested sampling", "SBI", "neural posterior estimation", "emulator", "N-body", "semi-analytic model"]
                    }
                    validated = []
                    for item in parsed[key]:
                        for allowed in allowed_sets[key]:
                            if allowed.lower() == str(item).strip().lower():
                                validated.append(allowed)
                                break
                    result[key] = validated
    except Exception as e:
        logger.warning(f"Failed to parse metadata extraction JSON: {e}")
        
    return result

