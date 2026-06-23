# Writing Custom Paper Sources for AURA

AURA has a modular architecture that allows you to easily ingest papers from new journals, archives, or internal research repositories. This is achieved by creating a custom plugin package and registering it under the `aura.sources` entry point group.

## 1. The `PaperSource` Interface

All paper sources must inherit from the `PaperSource` abstract base class located in [fetcher.py](file:///home/bmxz31/Projects/aura/aura/fetcher.py). You must implement two abstract methods:

- `fetch(self, categories: list[str], max_results: int = 200, days_back: int = 1) -> list[dict]`
- `fetch_simple(self, categories: list[str], max_results: int = 200) -> list[dict]`

Additionally, you can optionally implement:
- `fetch_by_id(self, paper_id: str) -> Optional[dict]` (returns `None` by default)

### Expected Paper Schema

Your source should return a list of dictionaries, where each dictionary represents a paper conforming to the following structure:

```python
{
    "arxiv_id": "unique-id",          # A globally unique string ID for the paper (e.g., "myjournal:12345")
    "title": "Paper Title",
    "abstract": "Paper abstract text...",
    "authors": ["Author One", "Author Two"], # Or a list of strings
    "categories": "category1, category2",
    "published": "2026-06-23T15:27:29Z", # ISO 8601 date string
    "url": "https://example.com/paper/12345",
    "pdf_url": "https://example.com/paper/12345.pdf", # Optional
    "source": "myjournal",            # Source identifier matching your entry point name
}
```

## 2. Example Implementation

Here is a complete template for a custom source (`my_source.py`):

```python
from typing import Optional
from aura.fetcher import PaperSource

class MyCustomJournalSource(PaperSource):
    """A custom source that fetches papers from a corporate internal repo."""

    def fetch(self, categories: list[str], max_results: int = 200, days_back: int = 1) -> list[dict]:
        # Implement recent papers fetching logic with date filter
        # ...
        return []

    def fetch_simple(self, categories: list[str], max_results: int = 200) -> list[dict]:
        # Implement simple keyword-based search or default list fetching
        # ...
        return []

    def fetch_by_id(self, paper_id: str) -> Optional[dict]:
        # Optionally implement single paper fetching
        return None
```

## 3. Registering the Source as a Package

To make AURA discover your custom source, package it as a standard Python package and define an entry point in `pyproject.toml` or `setup.cfg`.

### Using `pyproject.toml` (Modern)

Add the entry point under the `[project.entry-points."aura.sources"]` table:

```toml
[project]
name = "aura-my-custom-source"
version = "0.1.0"
dependencies = [
    "requests"
]

[project.entry-points."aura.sources"]
my_source = "my_package.my_source:MyCustomJournalSource"
```

### Using `setup.cfg` (Legacy)

```ini
[options.entry_points]
aura.sources =
    my_source = my_package.my_source:MyCustomJournalSource
```

## 4. Discovery and Configuration

AURA discovers all sources registered under `aura.sources` using `importlib.metadata` on startup. 

By default, newly discovered sources are **disabled** unless explicitly enabled in `config.yaml`. To enable your custom source, add it to your configuration file:

```yaml
sources_config:
  my_source: true
```

The key `my_source` matches the entry point name you defined during packaging.
