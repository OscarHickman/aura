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
                error_str = str(error).lower()
                if "429" in error_str or "rate limit" in error_str or "too many requests" in error_str:
                    logger.warning("Groq rate limit hit (429); skipping to next provider.")
                    return None
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
    payload: Any = {
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


def extract_text_from_pdf_url(pdf_url: str) -> str:
    """Download PDF from URL and extract plain text."""
    logger.info(f"Downloading PDF from {pdf_url}...")
    headers = {
        "User-Agent": "AURA Research Assistant (https://github.com/OscarHickman/aura)"
    }
    response = requests.get(pdf_url, headers=headers, timeout=30)
    response.raise_for_status()
    
    # Load PDF bytes in pypdf
    from pypdf import PdfReader
    import io
    pdf_file = io.BytesIO(response.content)
    reader = PdfReader(pdf_file)
    
    text_parts = []
    # Extract text from all pages
    for page in reader.pages:
        page_text = page.extract_text()
        if page_text:
            text_parts.append(page_text)
            
    return "\n".join(text_parts)


def generate_full_summary(
    arxiv_id: str,
    pdf_url: str,
    mode: str = "grad_student",
    provider: Optional[str] = None,
    api_key: Optional[str] = None,
) -> str:
    """Download the paper's PDF, extract text, and generate a structured deep-dive summary."""
    try:
        text = extract_text_from_pdf_url(pdf_url)
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

    # Call LLM provider
    providers_to_try = [provider.lower()] if provider else _load_providers_order()
    
    for p in providers_to_try:
        try:
            if p == "groq":
                from groq import Groq
                resolved_key = _resolve_api_key(api_key, "GROQ_API_KEY", "groq")
                if not resolved_key:
                    continue
                client = Groq(api_key=resolved_key)
                model_name = _get_provider_setting("groq", "model") or "llama-3.3-70b-versatile"
                message = client.chat.completions.create(
                    messages=[{"role": "user", "content": prompt}],
                    model=model_name,
                    max_tokens=1000,
                    temperature=0.3,
                )
                return message.choices[0].message.content.strip()

            elif p == "google":
                resolved_key = _resolve_api_key(api_key, "GOOGLE_API_KEY", "google")
                if not resolved_key:
                    continue
                endpoint = (
                    "https://generativelanguage.googleapis.com/v1beta/"
                    f"models/gemini-2.0-flash:generateContent?key={resolved_key}"
                )
                payload = {
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"temperature": 0.3, "maxOutputTokens": 1000},
                }
                response = requests.post(endpoint, json=payload, timeout=30)
                response.raise_for_status()
                data = response.json()
                candidates = data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    return "".join(part.get("text", "") for part in parts).strip()

            elif p == "openai":
                from openai import OpenAI
                resolved_key = _resolve_api_key(api_key, "OPENAI_API_KEY", "openai")
                if not resolved_key:
                    continue
                client = OpenAI(api_key=resolved_key)
                response = client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=1000,
                    temperature=0.3,
                )
                return response.choices[0].message.content.strip()

            elif p == "anthropic":
                import anthropic
                resolved_key = _resolve_api_key(api_key, "ANTHROPIC_API_KEY", "anthropic")
                if not resolved_key:
                    continue
                client = anthropic.Anthropic(api_key=resolved_key)
                message = client.messages.create(
                    model="claude-3-5-sonnet-20241022",
                    max_tokens=1000,
                    messages=[{"role": "user", "content": prompt}],
                )
                return message.content[0].text.strip()
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
    # Limit full text size to prevent context overflow (approx 40k characters)
    truncated_text = full_text[:40000]
    
    prompt = (
        f"You are a helpful research assistant. Answer the user's question about the research paper (arxiv ID {arxiv_id}) "
        f"using the provided full text of the paper. Always use UK-English spelling (e.g., colour, prioritising, analysing).\n\n"
        f"Here is the text extracted from the paper:\n"
        f"---\n"
        f"{truncated_text}\n"
        f"---\n\n"
        f"Question: {question}\n"
        f"Answer:"
    )

    providers_to_try = [provider.lower()] if provider else _load_providers_order()
    
    for p in providers_to_try:
        try:
            if p == "groq":
                from groq import Groq
                resolved_key = _resolve_api_key(api_key, "GROQ_API_KEY", "groq")
                if not resolved_key:
                    continue
                client = Groq(api_key=resolved_key)
                model_name = _get_provider_setting("groq", "model") or "llama-3.3-70b-versatile"
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

            elif p == "google":
                resolved_key = _resolve_api_key(api_key, "GOOGLE_API_KEY", "google")
                if not resolved_key:
                    continue
                endpoint = (
                    "https://generativelanguage.googleapis.com/v1beta/"
                    f"models/gemini-2.0-flash:streamGenerateContent?key={resolved_key}"
                )
                payload = {
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

            elif p == "openai":
                from openai import OpenAI
                resolved_key = _resolve_api_key(api_key, "OPENAI_API_KEY", "openai")
                if not resolved_key:
                    continue
                client = OpenAI(api_key=resolved_key)
                stream = client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[{"role": "user", "content": prompt}],
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

            elif p == "anthropic":
                import anthropic
                resolved_key = _resolve_api_key(api_key, "ANTHROPIC_API_KEY", "anthropic")
                if not resolved_key:
                    continue
                client = anthropic.Anthropic(api_key=resolved_key)
                has_yielded = False
                with client.messages.stream(
                    model="claude-3-5-sonnet-20241022",
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
    providers_to_try = [provider.lower()] if provider else _load_providers_order()

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
                        return message.choices[0].message.content.strip()
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
                candidate_models = [m for m in [configured_model, "gemini-1.5-flash", "gemini-2.5-flash"] if m]
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

            elif p == "openai":
                try:
                    from openai import OpenAI
                except ImportError:
                    continue
                key = _resolve_api_key(api_key, "OPENAI_API_KEY", "openai")
                if not key:
                    continue
                client = OpenAI(api_key=key)
                configured_model = _get_provider_setting("openai", "model")
                model_name = configured_model or "gpt-4o-mini"
                try:
                    message = client.chat.completions.create(
                        messages=[{"role": "user", "content": prompt}],
                        model=model_name,
                        max_tokens=max_tokens,
                        temperature=temperature,
                    )
                    return message.choices[0].message.content.strip()
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
    
    result = {"observables": [], "datasets": [], "methods": []}
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

