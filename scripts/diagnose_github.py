from dotenv import load_dotenv
load_dotenv()

import os
from github import Github, GithubException

def diagnose():
    token = os.getenv("COPILOT_GITHUB_TOKEN")
    repo_name = os.getenv("GITHUB_REPO_NAME")

    print(f"Token present: {bool(token)}")
    if token:
        print(f"Token length: {len(token)}")
        print(f"Token prefix: {token[:4]}...")

    print(f"Repo Name: {repo_name}")

    if not token:
        print("ERROR: No token found.")
        return

    g = Github(token)

    print("\n--- 1. Check User ---")
    try:
        user = g.get_user()
        print(f"Authenticated as: {user.login}")
    except GithubException as e:
        print(f"Failed to get user: {e}")
        return

    print("\n--- 2. Check Repo Access ---")
    try:
        repo = g.get_repo(repo_name)
        print(f"Repo found: {repo.full_name}")
        print(f"Private: {repo.private}")
        print(f"Permissions: {repo.permissions}")
    except GithubException as e:
        print(f"Failed to get repo '{repo_name}': {e}")
        if e.status == 404:
            print("HINT: 404 means either the repo doesn't exist OR the token lacks 'repo' scope to see it.")

if __name__ == "__main__":
    diagnose()
