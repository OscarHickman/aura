"""GitHub metadata fetching utilities for AURA."""

import logging
import os
import re
import requests
from typing import Optional, Any

logger = logging.getLogger(__name__)


def extract_github_url(text: str) -> Optional[str]:
    """Extract a GitHub repository URL from text.

    Returns the cleaned canonical HTTPS URL if found.
    """
    if not text:
        return None
    # Match pattern like github.com/owner/repo
    match = re.search(
        r"(https?://)?(www\.)?github\.com/([\w\-\.]+)/([\w\-\.]+)",
        text,
        re.IGNORECASE,
    )
    if match:
        owner = match.group(3)
        repo = match.group(4)
        # Strip trailing punctuation that might be captured from text sentences
        for char in [".", ",", ")", "]", "}", "/"]:
            if repo.endswith(char):
                repo = repo[:-1]
        if repo.endswith(".git"):
            repo = repo[:-4]
        return f"https://github.com/{owner}/{repo}"
    return None


def fetch_github_metadata(
    repo_url: str, token: Optional[str] = None
) -> Optional[dict[str, Any]]:
    """Fetch repository metadata (stars, last commit, language) from the GitHub API.

    Gracefully handles rate limits and API failures.
    """
    if not repo_url:
        return None

    # Parse owner and repo name
    match = re.search(
        r"github\.com/([\w\-\.]+)/([\w\-\.]+)", repo_url, re.IGNORECASE
    )
    if not match:
        logger.warning(
            f"Could not parse GitHub owner/repository from URL: {repo_url}"
        )
        return None

    owner = match.group(1)
    repo = match.group(2)

    # Clean the repo name of trailing punctuation
    for char in [".", ",", ")", "]", "}", "/"]:
        if repo.endswith(char):
            repo = repo[:-1]
    if repo.endswith(".git"):
        repo = repo[:-4]

    api_url = f"https://api.github.com/repos/{owner}/{repo}"
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "AURA-Research-Assistant (https://github.com/OscarHickman/aura)",
    }

    # Add authorisation token if provided or set in environment variables
    token = token or os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"token {token}"

    try:
        resp = requests.get(api_url, headers=headers, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            return {
                "repo_url": f"https://github.com/{owner}/{repo}",
                "stars": data.get("stargazers_count", 0),
                "last_commit": data.get("pushed_at"),
                "language": data.get("language"),
            }
        elif resp.status_code in (403, 429):
            logger.warning(
                f"GitHub API rate limit exceeded or forbidden for {repo_url}: {resp.text}"
            )
        else:
            logger.warning(
                f"GitHub API returned status code {resp.status_code} for {repo_url}"
            )
    except requests.RequestException as e:
        logger.error(f"Failed to fetch GitHub metadata for {repo_url}: {e}")

    return None
