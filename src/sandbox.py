"""Fork, clone, and configure a GitHub sandbox repo for agent use.

Handles:
  1. Forking the upstream repo under the configured GitHub user
  2. Cloning the fork with push credentials
  3. Configuring git identity and upstream remote
"""

import json
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.request
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


def _fork_exists(owner: str, repo: str, token: str) -> bool:
    """Check if a repo exists and is accessible."""
    try:
        _gh_api("GET", f"/repos/{owner}/{repo}", token)
        return True
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return False
        raise


def _ensure_fork(upstream_owner: str, repo_name: str,
                 gh_user: str, token: str) -> None:
    """Create a fork if it doesn't exist, then wait until it's ready."""
    if _fork_exists(gh_user, repo_name, token):
        print(f"Fork {gh_user}/{repo_name} already exists")
        return

    print(f"Forking {upstream_owner}/{repo_name} → {gh_user}/{repo_name} ...")
    try:
        _gh_api("POST", f"/repos/{upstream_owner}/{repo_name}/forks",
                token, body={})
    except urllib.error.HTTPError as e:
        # 202 Accepted is the normal fork-creation response
        if e.code != 202:
            raise

    # Poll until the fork is accessible
    deadline = time.time() + 60
    while time.time() < deadline:
        if _fork_exists(gh_user, repo_name, token):
            print(f"Fork ready: {gh_user}/{repo_name}")
            return
        time.sleep(3)
    raise TimeoutError(f"Fork {gh_user}/{repo_name} not ready after 60s")


def _sync_fork(gh_user: str, repo_name: str, token: str,
               branch: str = "main") -> None:
    """Sync fork's default branch with upstream."""
    try:
        _gh_api("POST", f"/repos/{gh_user}/{repo_name}/merge-upstream",
                token, body={"branch": branch})
        print("Fork synced with upstream")
    except urllib.error.HTTPError:
        print("Fork sync skipped (may already be up to date)")


def setup_sandbox(
    upstream_repo: str = DEFAULT_UPSTREAM,
    sandbox_dir: Path | str = DEFAULT_SANDBOX_DIR,
) -> Path:
    """Fork upstream, clone fork with push access, configure git.

    Returns the sandbox directory path.
    """
    gh_user, gh_token = _load_github_creds()
    upstream_owner, repo_name = upstream_repo.split("/")
    sandbox = Path(sandbox_dir)

    # 1. Ensure fork exists
    _ensure_fork(upstream_owner, repo_name, gh_user, gh_token)

    # 2. Sync fork with upstream
    _sync_fork(gh_user, repo_name, gh_token)

    # 3. Clone the fork with credentials
    clone_url = (
        f"https://{gh_user}:{gh_token}@github.com"
        f"/{gh_user}/{repo_name}.git"
    )
    if sandbox.exists():
        shutil.rmtree(sandbox)

    print(f"Cloning fork to {sandbox} ...")
    subprocess.run(
        ["git", "clone", clone_url, str(sandbox)],
        check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )

    # 4. Configure git inside the sandbox
    def git(*args: str) -> None:
        subprocess.run(
            ["git", *args], cwd=str(sandbox), check=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )

    git("config", "user.name", gh_user)
    git("config", "user.email", f"{gh_user}@users.noreply.github.com")
    git("remote", "add", "upstream",
        f"https://github.com/{upstream_owner}/{repo_name}.git")

    print(f"Sandbox ready: {sandbox}")
    print(f"  origin   → {gh_user}/{repo_name} (push enabled)")
    print(f"  upstream → {upstream_owner}/{repo_name}")

    return sandbox
