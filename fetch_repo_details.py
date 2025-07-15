import requests
import csv
import os
import time
from datetime import datetime
from dotenv import load_dotenv
from requests.exceptions import ConnectionError, ChunkedEncodingError

load_dotenv()
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
ORG_NAME = os.getenv("ORG_NAME")
HEADERS = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json"
}

def log_error(msg):
    with open("error_log.txt", "a") as f:
        f.write(f"{datetime.now()} - {msg}\n")

def github_api_get(url, params=None, max_retries=5):
    retries = 0
    while retries < max_retries:
        try:
            response = requests.get(url, headers=HEADERS, params=params)
            if response.status_code == 403 and "rate limit" in response.text.lower():
                reset_time = int(response.headers.get("X-RateLimit-Reset", time.time() + 60))
                sleep_time = max(reset_time - int(time.time()), 1)
                print(f"Rate limit hit. Sleeping for {sleep_time} seconds...")
                time.sleep(sleep_time)
                continue
            if response.status_code not in (200, 201):
                log_error(f"Failed GET {url}: {response.status_code} {response.text}")
                return None
            return response.json()
        except (ConnectionError, ChunkedEncodingError) as e:
            retries += 1
            log_error(f"Connection error on {url}: {e}. Retry {retries}/{max_retries}")
            time.sleep(5 * retries)  # Exponential backoff
        except Exception as e:
            log_error(f"Unexpected error on {url}: {e}")
            return None
    log_error(f"Max retries exceeded for {url}")
    return None

def get_repos(org):
    repos = []
    page = 1
    per_page = 100
    while True:
        url = f"https://api.github.com/orgs/{org}/repos"
        params = {"per_page": per_page, "page": page, "type": "all"}
        data = github_api_get(url, params)
        if not data:
            break
        repos.extend(data)
        if len(data) < per_page:
            break
        page += 1
    return repos

def get_pr_counts(org, repo):
    url = f"https://api.github.com/repos/{org}/{repo}/pulls"
    open_prs = github_api_get(url, {"state": "open", "per_page": 1})
    closed_prs = github_api_get(url, {"state": "closed", "per_page": 1})
    merged_prs = 0
    closed_count = len(closed_prs) if closed_prs else 0
    if closed_prs:
        # GitHub doesn't provide merged PR count directly, so we have to iterate (slow for many PRs)
        page = 1
        per_page = 100
        while True:
            prs = github_api_get(url, {"state": "closed", "per_page": per_page, "page": page})
            if not prs:
                break
            for pr in prs:
                pr_url = f"https://api.github.com/repos/{org}/{repo}/pulls/{pr['number']}"
                pr_data = github_api_get(pr_url)
                if pr_data and pr_data.get("merged_at"):
                    merged_prs += 1
            if len(prs) < per_page:
                break
            page += 1
    return len(open_prs) if open_prs else 0, closed_count, merged_prs

def get_issue_counts(org, repo):
    url = f"https://api.github.com/repos/{org}/{repo}/issues"
    open_issues = github_api_get(url, {"state": "open", "per_page": 1})
    closed_issues = github_api_get(url, {"state": "closed", "per_page": 1})
    # Only issues, not PRs
    def count_issues(state):
        page = 1
        per_page = 100
        count = 0
        while True:
            issues = github_api_get(url, {"state": state, "per_page": per_page, "page": page})
            if not issues:
                break
            count += sum(1 for i in issues if "pull_request" not in i)
            if len(issues) < per_page:
                break
            page += 1
        return count
    return count_issues("open"), count_issues("closed")

def get_branches(org, repo):
    url = f"https://api.github.com/repos/{org}/{repo}/branches"
    branches = []
    page = 1
    per_page = 100
    while True:
        data = github_api_get(url, {"per_page": per_page, "page": page})
        if not data:
            break
        branches.extend(data)
        if len(data) < per_page:
            break
        page += 1
    return len(branches)

def get_tags(org, repo):
    url = f"https://api.github.com/repos/{org}/{repo}/tags"
    tags = []
    page = 1
    per_page = 100
    while True:
        data = github_api_get(url, {"per_page": per_page, "page": page})
        if not data:
            break
        tags.extend(data)
        if len(data) < per_page:
            break
        page += 1
    return len(tags)

def get_last_commit(org, repo, default_branch):
    url = f"https://api.github.com/repos/{org}/{repo}/commits"
    data = github_api_get(url, {"sha": default_branch, "per_page": 1})
    if data and len(data) > 0:
        commit = data[0]
        date = commit["commit"]["committer"]["date"]
        user = commit["commit"]["committer"]["name"]
        return date, user
    return "", ""

def get_primary_language(repo_data):
    return repo_data.get("language", "")

def main():
    org = ORG_NAME
    if not org:
        print("ORG_NAME not set in .env file.")
        return
    repos = get_repos(org)
    if not repos:
        print("No repositories found or error occurred.")
        return

    filename = f"{org}_repo_details_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
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
                open_prs, closed_prs, merged_prs = get_pr_counts(org, repo["name"])
                open_issues, closed_issues = get_issue_counts(org, repo["name"])
                branch_count = get_branches(org, repo["name"])
                tag_count = get_tags(org, repo["name"])
                last_commit_date, last_commit_user = get_last_commit(org, repo["name"], repo["default_branch"])
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
                    "Total Releases": repo["open_issues_count"],  # fallback, see below
                    "Total Tags": tag_count,
                    "Last Committed Date": last_commit_date,
                    "Last Committed User": last_commit_user
                }
                # Releases count
                releases_url = f"https://api.github.com/repos/{org}/{repo['name']}/releases"
                releases = github_api_get(releases_url, {"per_page": 1})
                row["Total Releases"] = len(releases) if releases else 0
                writer.writerow(row)
            except Exception as e:
                log_error(f"Error processing {repo['name']}: {e}")
                continue

    print(f"Done. Output written to {filename}")

if __name__ == "__main__":
    main()
