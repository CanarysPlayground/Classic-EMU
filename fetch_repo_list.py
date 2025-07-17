import os
from dotenv import load_dotenv
import requests
import csv
import time
import logging

# Create logs directory if it doesn't exist
os.makedirs("logs", exist_ok=True)

# Configure logging
logging.basicConfig(
    filename="logs/fetch_repos.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

# === Load GitHub credentials ===

# Step 1: Try GitHub Actions secrets (passed as env vars)
GH_ORG = os.getenv("GH_ORG")
GH_PAT = os.getenv("GH_PAT")

# Step 2: Fallback to .env file in repo root
if not GH_ORG or not GH_PAT:
    load_dotenv()  # loads .env variables into environment
    GH_ORG = GH_ORG or os.getenv("GH_ORG")
    GH_PAT = GH_PAT or os.getenv("GH_PAT")

if not GH_ORG or not GH_PAT:
    print("❌ Error: Please set GH_ORG and GH_PAT as GitHub Secrets or in your .env file.")
    logging.error("Missing GH_ORG or GH_PAT environment variables.")
    exit(1)

def get_github_repos(org, token, per_page=100):
    url = f"https://api.github.com/orgs/{org}/repos"
    headers = {"Authorization": f"token {token}"}
    params = {"per_page": per_page, "page": 1}
    repos = []

    while True:
        response = requests.get(url, headers=headers, params=params)
        if response.status_code == 403 and "X-RateLimit-Remaining" in response.headers:
            reset_time = int(response.headers.get("X-RateLimit-Reset", 0))
            wait_seconds = max(reset_time - int(time.time()), 1)
            msg = f"⚠️ Rate limit exceeded. Waiting for {wait_seconds} seconds..."
            print(msg)
            logging.warning(msg)
            time.sleep(wait_seconds)
            continue
        elif response.status_code != 200:
            error_msg = f"❌ Error: {response.status_code} - {response.json().get('message', 'Unknown error')}"
            print(error_msg)
            logging.error(error_msg)
            break

        data = response.json()
        if not data:
            break

        repos.extend(data)
        params["page"] += 1

    return repos

def save_to_csv(repositories, filename="github_repos.csv"):
    with open(filename, mode="w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(["Repository Name", "Visibility"])
        for repo in repositories:
            writer.writerow([repo["name"], repo.get("visibility", "N/A")])

if __name__ == "__main__":
    try:
        print(f"🔍 Fetching repositories for org: {GH_ORG}")
        repositories = get_github_repos(GH_ORG, GH_PAT)
        save_to_csv(repositories)
        print("✅ CSV file saved successfully!")
        logging.info("CSV file saved successfully.")
    except Exception as e:
        logging.exception(f"Unhandled exception: {e}")
        print("❌ An error occurred. Check logs/fetch_repos.log for details.")
