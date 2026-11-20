
import re
import requests

GITHUB_API = "https://api.github.com"
WORKFLOW_FILE = "ci-cd.yml"


def get_repository_details(repo_url):
    match = re.match(
        r"https?://github\.com/([^/]+)/([^/]+)/?$",
        repo_url.strip()
    )

    if not match:
        raise ValueError("Invalid GitHub repository URL")

    owner, repo = match.groups()
    return owner, repo.removesuffix(".git")


def get_headers(token):
    if not token:
        raise ValueError("GitHub token is missing. Configure GITHUB_TOKEN.")

    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28"
    }


def trigger_pipeline(repo_url, branch, token):
    owner, repo = get_repository_details(repo_url)

    if not branch:
        raise ValueError("Branch name is required")

    url = (
        f"{GITHUB_API}/repos/{owner}/{repo}"
        f"/actions/workflows/{WORKFLOW_FILE}/dispatches"
    )

    response = requests.post(
        url,
        headers=get_headers(token),
        json={"ref": branch},
        timeout=20
    )

    if response.status_code != 204:
        raise RuntimeError(
            f"GitHub API error ({response.status_code}): "
            f"{response.text[:500]}"
        )

    return {
        "success": True,
        "message": "Pipeline successfully submitted to GitHub Actions",
        "repository": f"{owner}/{repo}",
        "branch": branch
    }


def get_pipeline_status(repo_url, branch, token):
    owner, repo = get_repository_details(repo_url)

    url = (
        f"{GITHUB_API}/repos/{owner}/{repo}"
        f"/actions/workflows/{WORKFLOW_FILE}/runs"
    )

    response = requests.get(
        url,
        headers=get_headers(token),
        params={
            "branch": branch,
            "per_page": 1,
            "event": "workflow_dispatch"
        },
        timeout=20
    )

    if response.status_code != 200:
        raise RuntimeError(
            f"GitHub API error ({response.status_code}): "
            f"{response.text[:500]}"
        )

    runs = response.json().get("workflow_runs", [])

    if not runs:
        return {
            "success": True,
            "status": "Not Started",
            "conclusion": None,
            "message": "No manually triggered pipeline found"
        }

    run = runs[0]

    return {
        "success": True,
        "run_id": run["id"],
        "status": run["status"],
        "conclusion": run.get("conclusion"),
        "branch": run["head_branch"],
        "commit": run["head_sha"][:7],
        "run_url": run["html_url"],
        "created_at": run["created_at"],
        "updated_at": run["updated_at"]
    }
