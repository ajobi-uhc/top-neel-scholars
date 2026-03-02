"""Create a fresh GitHub repo per agent run and populate it from the upstream template.

Each run gets a unique repo named {provider}_{mode}_{timestamp} under
the configured GITHUB_USER account.
"""

import json
import os
import shutil
import subprocess
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"

DEFAULT_UPSTREAM = "divanoval/top-scholar-sandbox"
DEFAULT_SANDBOX_DIR = Path.home() / "sandbox"


def _load_github_creds() -> tuple[str, str]:
    """Load GITHUB_USER and GITHUB_TOKEN from .env or environment."""
    env: dict[str, str] = {}
    if _ENV_FILE.exists():
        for line in _ENV_FILE.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, val = line.partition("=")
                env[key.strip()] = val.strip().strip('"').strip("'")
    # Environment variables take precedence
    for key in ("GITHUB_USER", "GITHUB_TOKEN"):
        if key in os.environ:
            env[key] = os.environ[key]

    user = env.get("GITHUB_USER", "")
    token = env.get("GITHUB_TOKEN", "")
    if not user or not token:
        raise RuntimeError(
            "GITHUB_USER and GITHUB_TOKEN must be set in .env or environment"
        )
    return user, token


def _gh_api(method: str, path: str, token: str,
            body: dict | None = None) -> dict:
    """Make a GitHub API request, return parsed JSON."""
    url = f"https://api.github.com{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"token {token}")
    req.add_header("Accept", "application/vnd.github+json")
    if data:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def _make_repo_name(provider: str, mode: str) -> str:
    """Generate a unique repo name like claude_baseline_2026-03-02T14-30-00."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
    return f"{provider}_{mode}_{ts}"


def setup_sandbox(
    provider: str = "claude",
    mode: str = "baseline",
    upstream_repo: str = DEFAULT_UPSTREAM,
    sandbox_dir: Path | str = DEFAULT_SANDBOX_DIR,
) -> Path:
    """Create a fresh repo from upstream content and return the sandbox path.

    Steps:
      1. Clone upstream (read-only, no auth needed)
      2. Create a new empty repo via GitHub API
      3. Re-init git, push upstream content to the new repo
    """
    gh_user, gh_token = _load_github_creds()
    repo_name = _make_repo_name(provider, mode)
    sandbox = Path(sandbox_dir)

    # 1. Clone upstream into sandbox dir
    if sandbox.exists():
        shutil.rmtree(sandbox)

    clone_url = f"https://github.com/{upstream_repo}.git"
    print(f"Cloning {upstream_repo} → {sandbox} ...")
    subprocess.run(
        ["git", "clone", clone_url, str(sandbox)],
        check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )

    # 2. Create new empty repo on GitHub
    print(f"Creating repo {gh_user}/{repo_name} ...")
    _gh_api("POST", "/user/repos", gh_token,
            body={"name": repo_name, "private": False})

    # 3. Replace .git, re-init, push content to the new repo
    shutil.rmtree(sandbox / ".git")

    def git(*args: str) -> None:
        subprocess.run(
            ["git", *args], cwd=str(sandbox), check=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )

    push_url = (
        f"https://{gh_user}:{gh_token}@github.com"
        f"/{gh_user}/{repo_name}.git"
    )

    git("init", "-b", "main")
    git("config", "user.name", gh_user)
    git("config", "user.email", f"{gh_user}@users.noreply.github.com")
    git("remote", "add", "origin", push_url)
    git("add", ".")
    git("commit", "-m", "Initial commit from top-scholar-sandbox")
    git("push", "-u", "origin", "main")

    # Copy .env into sandbox so the agent has access to API keys (e.g. OPENROUTER_API_KEY)
    if not _ENV_FILE.exists():
        raise FileNotFoundError(f".env file not found at {_ENV_FILE}")
    shutil.copy2(_ENV_FILE, sandbox / ".env")
    print(f"  .env copied into sandbox")

    print(f"Sandbox ready: {sandbox}")
    print(f"  repo → {gh_user}/{repo_name}")

    return sandbox
