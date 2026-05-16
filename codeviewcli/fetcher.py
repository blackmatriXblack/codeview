"""URL fetcher for code hosting platforms.

Supports: GitHub, GitLab, Bitbucket, Gitee, GitCode, SourceForge, and raw URLs.
Automatically resolves branches and extracts file content.
"""

import re
import os
import tempfile
from pathlib import Path
from typing import Optional, Dict, Tuple, List
from urllib.parse import urlparse, urljoin

import requests
from bs4 import BeautifulSoup

# Session with browser-like headers
session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
})


class FetcherError(Exception):
    """Custom exception for fetch errors."""
    pass


def parse_url(url: str) -> Dict[str, str]:
    """Parse a code hosting URL and extract platform, owner, repo, branch, and file path."""
    parsed = urlparse(url)
    host = parsed.hostname.lower() if parsed.hostname else ""

    result = {
        "platform": "unknown",
        "host": host,
        "owner": "",
        "repo": "",
        "branch": "",
        "file_path": "",
        "raw_url": "",
    }

    # GitHub
    if "github.com" in host:
        result["platform"] = "github"
        parts = parsed.path.strip("/").split("/")
        if len(parts) >= 3 and parts[2] == "blob":
            result["owner"] = parts[0]
            result["repo"] = parts[1]
            result["branch"] = parts[3]
            result["file_path"] = "/".join(parts[4:])
            result["raw_url"] = (
                f"https://raw.githubusercontent.com/{parts[0]}/{parts[1]}"
                f"/{parts[3]}/{'/'.join(parts[4:])}"
            )
        elif len(parts) >= 2:
            result["owner"] = parts[0]
            result["repo"] = parts[1].replace(".git", "")

    # GitLab
    elif "gitlab.com" in host:
        result["platform"] = "gitlab"
        parts = parsed.path.strip("/").split("/")
        if len(parts) >= 4 and parts[2] == "-" and parts[3] == "blob":
            # GitLab format: /owner/repo/-/blob/branch/path
            result["owner"] = parts[0]
            result["repo"] = parts[1]
            result["branch"] = parts[4]
            result["file_path"] = "/".join(parts[5:])
            result["raw_url"] = (
                f"https://gitlab.com/{parts[0]}/{parts[1]}/-/raw"
                f"/{parts[4]}/{'/'.join(parts[5:])}"
            )
        elif len(parts) >= 2:
            result["owner"] = parts[0]
            result["repo"] = parts[1].replace(".git", "")

    # Bitbucket
    elif "bitbucket.org" in host:
        result["platform"] = "bitbucket"
        parts = parsed.path.strip("/").split("/")
        if len(parts) >= 3 and parts[2] == "src":
            result["owner"] = parts[0]
            result["repo"] = parts[1]
            result["branch"] = parts[3]
            result["file_path"] = "/".join(parts[4:])
            result["raw_url"] = (
                f"https://bitbucket.org/{parts[0]}/{parts[1]}/raw"
                f"/{parts[3]}/{'/'.join(parts[4:])}"
            )
        elif len(parts) >= 2:
            result["owner"] = parts[0]
            result["repo"] = parts[1].replace(".git", "")

    # Gitee (China)
    elif "gitee.com" in host:
        result["platform"] = "gitee"
        parts = parsed.path.strip("/").split("/")
        if len(parts) >= 3 and parts[2] == "blob":
            result["owner"] = parts[0]
            result["repo"] = parts[1]
            result["branch"] = parts[3]
            result["file_path"] = "/".join(parts[4:])
            result["raw_url"] = (
                f"https://gitee.com/{parts[0]}/{parts[1]}/raw"
                f"/{parts[3]}/{'/'.join(parts[4:])}"
            )
        elif len(parts) >= 2:
            result["owner"] = parts[0]
            result["repo"] = parts[1].replace(".git", "")

    # GitCode (China)
    elif "gitcode.com" in host:
        result["platform"] = "gitcode"
        parts = parsed.path.strip("/").split("/")
        if len(parts) >= 2:
            result["owner"] = parts[0]
            result["repo"] = parts[1].replace(".git", "")

    # SourceForge
    elif "sourceforge.net" in host:
        result["platform"] = "sourceforge"

    # Raw GitHub content
    elif "raw.githubusercontent.com" in host:
        result["platform"] = "github_raw"
        result["raw_url"] = url

    else:
        result["raw_url"] = url

    return result


def fetch_raw_content(url: str, timeout: int = 30) -> Tuple[str, str]:
    """Fetch raw file content from a URL. Returns (content, suggested_filename)."""
    try:
        response = session.get(url, timeout=timeout, allow_redirects=True)
        response.raise_for_status()

        # Check if it's HTML (not raw content)
        content_type = response.headers.get("Content-Type", "").lower()
        if "text/html" in content_type and "raw" not in url.lower():
            return _extract_from_html(response.text, url)

        # Extract filename from URL or Content-Disposition
        filename = ""
        parsed = urlparse(url)
        path_parts = parsed.path.strip("/").split("/")
        if path_parts:
            filename = path_parts[-1]

        cd = response.headers.get("Content-Disposition", "")
        if "filename=" in cd:
            match = re.search(r'filename[^;=\n]*=["\']?([^"\';\n]*)', cd)
            if match:
                filename = match.group(1)

        return response.text, filename

    except requests.RequestException as e:
        raise FetcherError(f"Failed to fetch URL: {e}")


def _extract_from_html(html: str, url: str) -> Tuple[str, str]:
    """Extract code from HTML page (e.g., GitHub blob page)."""
    soup = BeautifulSoup(html, "lxml")

    # Try GitHub-style code blocks
    for selector in [
        ".blob-wrapper table",
        ".js-file-line-container table",
        "#readme .markdown-body pre",
        "pre code",
        ".highlight pre",
        ".code-block pre",
    ]:
        elements = soup.select(selector)
        if elements:
            lines = []
            for el in elements:
                text = el.get_text()
                lines.append(text)
            content = "\n".join(lines)
            if content.strip():
                filename = urlparse(url).path.strip("/").split("/")[-1]
                return content, filename

    # Fallback: get all text
    body = soup.find("body")
    if body:
        text = body.get_text()
        return text, ""

    raise FetcherError("Could not extract code from HTML page")


def fetch_repo_file(url: str) -> Tuple[str, str, str]:
    """
    Smart fetch that handles code hosting URLs.
    Returns (content, filename, detected_language).
    """
    info = parse_url(url)

    # If we have a raw URL, use it directly
    if info["raw_url"]:
        try:
            content, filename = fetch_raw_content(info["raw_url"])
            return content, filename, ""
        except FetcherError:
            pass

    # Try the original URL
    try:
        content, filename = fetch_raw_content(url)
        return content, filename, ""
    except FetcherError as e:
        raise FetcherError(
            f"Could not fetch code from {info['platform']}. "
            f"Make sure the URL points to a valid file. Error: {e}"
        )


def fetch_github_repo_tree(owner: str, repo: str, branch: str = "main") -> List[str]:
    """Fetch the file tree of a GitHub repository using the API."""
    api_url = f"https://api.github.com/repos/{owner}/{repo}/git/trees/{branch}?recursive=1"
    try:
        response = session.get(api_url, timeout=30)
        response.raise_for_status()
        data = response.json()
        return [item["path"] for item in data.get("tree", []) if item["type"] == "blob"]
    except requests.RequestException:
        return []


def fetch_gitlab_repo_tree(owner: str, repo: str, branch: str = "main") -> List[str]:
    """Fetch the file tree of a GitLab repository using the API."""
    api_url = f"https://gitlab.com/api/v4/projects/{owner}%2F{repo}/repository/tree?recursive=true&ref={branch}"
    try:
        response = session.get(api_url, timeout=30)
        response.raise_for_status()
        data = response.json()
        return [item["path"] for item in data if item["type"] == "blob"]
    except requests.RequestException:
        return []


def fetch_gitee_repo_tree(owner: str, repo: str, branch: str = "master") -> List[str]:
    """Fetch the file tree of a Gitee repository."""
    api_url = f"https://gitee.com/api/v5/repos/{owner}/{repo}/git/trees/{branch}?recursive=1"
    try:
        response = session.get(api_url, timeout=30)
        response.raise_for_status()
        data = response.json()
        return [item["path"] for item in data.get("tree", []) if item["type"] == "blob"]
    except requests.RequestException:
        return []


def fetch_repo_tree(url: str) -> Tuple[List[str], str, str, str]:
    """Fetch the file tree from any supported platform URL. Returns (files, platform, owner, repo)."""
    info = parse_url(url)
    platform = info["platform"]
    owner = info["owner"]
    repo = info["repo"]

    if not owner or not repo:
        raise FetcherError("Could not determine owner/repo from the URL")

    branch = info["branch"] or "main"

    if platform == "github":
        files = fetch_github_repo_tree(owner, repo, branch)
    elif platform == "gitlab":
        files = fetch_gitlab_repo_tree(owner, repo, branch)
    elif platform == "gitee":
        files = fetch_gitee_repo_tree(owner, repo, branch)
    else:
        raise FetcherError(f"Repository tree browsing not supported for {platform}")

    if not files:
        raise FetcherError(f"No files found in {owner}/{repo} on branch {branch}")

    return files, platform, owner, repo


def is_code_hosting_url(url: str) -> bool:
    """Check if a URL is from a known code hosting platform."""
    host = urlparse(url).hostname or ""
    known_hosts = [
        "github.com", "gitlab.com", "bitbucket.org",
        "gitee.com", "gitcode.com", "sourceforge.net",
        "raw.githubusercontent.com",
    ]
    return any(h in host for h in known_hosts)
