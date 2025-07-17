import requests
import csv
import os
import time
from datetime import datetime
from dotenv import load_dotenv
from requests.exceptions import ConnectionError, ChunkedEncodingError

# Load .env variables
load_dotenv()

# Load secrets with fallback to .env
GH_PAT = os.getenv("GH_PAT")
GH_ORG = os.getenv("GH_ORG")

if not GH_PAT or not GH_ORG:
    print("❌ GH_PAT or GH_ORG not set. Please provide them in GitHub Secrets or a .env file.")
    exit(1)

HEADERS = {
    "Authorization": f"token {GH_PAT}",
    "Accept": "application/vnd.github+json"
}

def log_error(msg):
    os.makedirs("logs", exist_ok=True)
    with open("logs/error_log.txt", "a") as f:
        f.write(f"{datetime.now()} - {msg}\n")

def github_api_get(url, params=None, retries=3):
    for attempt in range(retries):
        try:
            response = requests.get(url, headers=HEADERS, params=params)
            if response.status_code == 403 and "X-RateLimit-Remaining" in response.headers and response.headers["X-RateLimit-Remaining"] == "0":
                reset_time = int(response.headers.get("X-RateLimit-Reset", time.time() + 60))
                sleep_time = reset_time - int(time.time())
                print(f"⏳ Rate limit hit. Sleeping for {sleep_time} seconds...")
                time.sleep(sleep_time)
                continue
            response.raise_for_status()
            return response.json()
        except (ConnectionError, ChunkedEncodingError) as e:
            print(f"🔁 Network error on attempt {attempt + 1}: {e}")
            time.sleep(2 ** attempt)
        except requests.RequestException as e:
            print(f"❌ Request failed: {e}")
            break
    return []

def get_repos(org):
    repos = []
    page = 1
    while True:
        url = f"https://api.github.com/orgs/{org}/repos"
        params = {"per_page": 100, "page": page}
        data = github_api_get(url, params)
        if not data:
            break
        repos.extend(data)
        if len(data) < 100:
            break
        page += 1
    return repos

def get_pr_counts(org, repo):
    url = f"https://api.github.com/repos/{org}/{repo}/pulls"
    open_prs = github_api_get(url, {"state": "open"})
    closed_prs = github_api_get(url, {"state": "closed"})
    merged_count = sum(1 for pr in closed_prs if pr.get("merged_at"))
    return len(open_prs), len(closed_prs), merged_count

def get_issue_counts(org, repo):
    issues_url = f"https://api.github.com/repos/{org}/{repo}/issues"
    open_issues = github_api_get(issues_url, {"state": "open"})
    closed_issues = github_api_get(issues_url, {"state": "closed"})
    open_issues = [i for i in open_issues if "pull_request" not in i]
    closed_issues = [i for i in closed_issues if "pull_request" not in i]
    return len(open_issues), len(closed_issues)

def get_branches(org, repo):
    url = f"https://api.github.com/repos/{org}/{repo}/branches"
    branches = github_api_get(url)
    return len(branches)

def get_tags(org, repo):
    url = f"https://api.github.com/repos/{org}/{repo}/tags"
    tags = github_api_get(url)
    return len(tags)

def get_last_commit(org, repo, default_branch):
    url = f"https://api.github.com/repos/{org}/{repo}/commits/{default_branch}"
    commit = github_api_get(url)
    if commit:
        date = commit["commit"]["committer"]["date"]
        author = commit["commit"]["committer"]["name"]
        return date, author
    return "", ""

def get_primary_language(repo):
    return repo.get("language", "N/A")

def main():
    repos = get_repos(GH_ORG)
    if not repos:
        print("No repositories found or error occurred.")
        return

    os.makedirs("output", exist_ok=True)
    filename = f"output/{GH_ORG}_repo_details.csv"

    with open(filename, "w", newline='', encoding="utf-8") as csvfile:
        fieldnames = [
            "Repo Name", "Visibility", "Created At", "Updated At", "Last Pushed Date", "Repo Size (MB)",
            "Primary Language", "Total Open PRs", "Total Closed PRs", "Total Merged PRs",
            "Total Open Issues", "Total Closed Issues", "Total Branches", "Total Releases",
            "Total Tags", "Last Committed Date", "Last Committed User"
        ]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()

        for repo in repos:
            print(f"Processing {repo['name']}...")
            try:
                open_prs, closed_prs, merged_prs = get_pr_counts(GH_ORG, repo["name"])
                open_issues, closed_issues = get_issue_counts(GH_ORG, repo["name"])
                branch_count = get_branches(GH_ORG, repo["name"])
                tag_count = get_tags(GH_ORG, repo["name"])
                last_commit_date, last_commit_user = get_last_commit(GH_ORG, repo["name"], repo["default_branch"])
                releases_url = f"https://api.github.com/repos/{GH_ORG}/{repo['name']}/releases"
                releases = github_api_get(releases_url, {"per_page": 1})

                row = {
                    "Repo Name": repo["name"],
                    "Visibility": repo["visibility"],
                    "Created At": repo["created_at"],
                    "Updated At": repo["updated_at"],
                    "Last Pushed Date": repo["pushed_at"],
                    "Repo Size (MB)": round(repo["size"] / 1024, 2),
                    "Primary Language": get_primary_language(repo),
                    "Total Open PRs": open_prs,
                    "Total Closed PRs": closed_prs,
                    "Total Merged PRs": merged_prs,
                    "Total Open Issues": open_issues,
                    "Total Closed Issues": closed_issues,
                    "Total Branches": branch_count,
                    "Total Releases": len(releases) if releases else 0,
                    "Total Tags": tag_count,
                    "Last Committed Date": last_commit_date,
                    "Last Committed User": last_commit_user
                }

                writer.writerow(row)

            except Exception as e:
                log_error(f"Error processing {repo['name']}: {e}")
                continue

    print(f"✅ Done. Output written to {filename}")

if __name__ == "__main__":
    main()
