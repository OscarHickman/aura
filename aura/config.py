import os
import json
import logging
from pathlib import Path
import yaml
from jsonschema import validate, ValidationError
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Load .env file at startup
load_dotenv()

SCHEMA_PATH = Path(__file__).parent / "config_schema.json"

def load_schema() -> dict:
    """Load the JSON Schema for AURA configuration."""
    with open(SCHEMA_PATH) as f:
        return json.load(f)

def load_config_file(config_path: str = "config.yaml") -> dict:
    """Load configuration from YAML file."""
    path = Path(config_path)
    if not path.exists():
        logger.warning(f"Config file '{config_path}' not found, using defaults.")
        return {}
    with open(path) as f:
        return yaml.safe_load(f) or {}

def get_validated_config(config_path: str = "config.yaml") -> dict:
    """Load, merge secrets from env/legacy files, and validate config against JSON Schema.
    
    Fails fast with ValueError if configuration requirements are not met.
    """
    config = load_config_file(config_path)
    
    # 1. Apply defaults if not present
    if "categories" not in config:
        config["categories"] = ["astro-ph.CO", "astro-ph.GA"]
    if "simulation_codes" not in config:
        config["simulation_codes"] = [
            "IllustrisTNG", "CAMELS", "EAGLE", "Millennium", "GADGET",
            "RAMSES", "GALFORM", "CAMB", "CLASS", "Cobaya", "emcee",
            "MultiNest", "PolyChord", "JAX", "sbi"
        ]
    if "data_dir" not in config:
        config["data_dir"] = "data"
    if "embedding_model" not in config:
        config["embedding_model"] = "all-MiniLM-L6-v2"
        
    config.setdefault("fetch", {}).setdefault("max_results", 200)
    config["fetch"].setdefault("days_back", 2)
    
    config.setdefault("summaries", {}).setdefault("generate_on_fetch", False)
    config["summaries"].setdefault("batch_size", 20)
    
    config.setdefault("scheduler", {}).setdefault("enabled", False)
    config["scheduler"].setdefault("fetch_hour", 6)
    config["scheduler"].setdefault("fetch_minute", 0)
    
    # Sources defaults
    sources = config.setdefault("sources", {})
    sources.setdefault("arxiv", True)
    sources.setdefault("semantic_scholar", True)
    sources.setdefault("biorxiv", True)
    sources.setdefault("rss", True)
    
    # Integrations defaults
    integrations = config.setdefault("integrations", {})
    slack = integrations.setdefault("slack", {})
    slack.setdefault("enabled", False)
    slack.setdefault("score_threshold", 0.8)
    
    discord = integrations.setdefault("discord", {})
    discord.setdefault("enabled", False)
    discord.setdefault("score_threshold", 0.8)

    # Vector store defaults
    vs = config.setdefault("vector_store", {})
    vs.setdefault("provider", "numpy")

    # Velocity alerts defaults
    va = config.setdefault("velocity_alerts", {})
    va.setdefault("enabled", True)
    va.setdefault("threshold", 5)
    if "keywords" not in va:
        va["keywords"] = list(config.get("simulation_codes", []))

    config.setdefault("collaborator_boost", 0.20)

    # 2. Merge Legacy and Env configurations
    email = config.setdefault("email", {})
    old_email_path = Path("user_credentials/email_config.json")
    if not any(email.values()) and old_email_path.exists():
        try:
            with open(old_email_path) as f:
                old_email = json.load(f)
                for k, v in old_email.items():
                    email.setdefault(k, v)
        except Exception:
            pass

    if os.environ.get("EMAIL_SMTP_PASSWORD"):
        email["smtp_password"] = os.environ.get("EMAIL_SMTP_PASSWORD")
    if os.environ.get("EMAIL_SMTP_USERNAME"):
        email["smtp_username"] = os.environ.get("EMAIL_SMTP_USERNAME")
        
    llm = config.setdefault("llm", {})
    # Legacy llm provider list from llm_providers.json
    old_providers_order = Path("user_credentials/llm_providers.json")
    if "providers_order" not in llm:
        if old_providers_order.exists():
            try:
                with open(old_providers_order) as f:
                    llm["providers_order"] = json.load(f).get("order", ["groq"])
            except Exception:
                llm["providers_order"] = ["groq"]
        else:
            llm["providers_order"] = ["groq"]
            
    providers = llm.setdefault("providers", {})
    legacy_providers = ["groq", "google", "openai", "anthropic"]
    for prov in legacy_providers:
        prov_config = providers.setdefault(prov, {})
        
        # Load from legacy file if key not set
        if "api_key" not in prov_config:
            old_prov_path = Path(f"user_credentials/{prov}_llm_config.json")
            if old_prov_path.exists():
                try:
                    with open(old_prov_path) as f:
                        old_data = json.load(f)
                        prov_config["api_key"] = old_data.get("api_key")
                        if old_data.get("model"):
                            prov_config["model"] = old_data.get("model")
                except Exception:
                    pass
                    
        # Overlay environment variables
        env_key_name = f"{prov.upper()}_API_KEY"
        if os.environ.get("LLM_API_KEY"):
            prov_config["api_key"] = os.environ.get("LLM_API_KEY")
        elif os.environ.get(env_key_name):
            prov_config["api_key"] = os.environ.get(env_key_name)
        elif prov == "google" and os.environ.get("GEMINI_API_KEY"):
            prov_config["api_key"] = os.environ.get("GEMINI_API_KEY")

    # 3. Validate JSON Schema
    schema = load_schema()
    try:
        validate(instance=config, schema=schema)
    except ValidationError as e:
        logger.error(f"Configuration validation failed: {e.message}")
        raise ValueError(f"Invalid configuration: {e.message}")
        
    # 4. Fail fast for required subfields
    if email and any(email.get(k) for k in email):
        if email.get("use_graph_api", False):
            required_email = ["from_email", "to_email", "ms_client_id"]
        else:
            required_email = ["smtp_host", "smtp_port", "smtp_username", "smtp_password", "from_email", "to_email"]
            
        missing_email = [k for k in required_email if not email.get(k)]
        if missing_email:
            raise ValueError(f"Missing required email config fields: {', '.join(missing_email)}")
            
    return config
