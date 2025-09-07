import os
import subprocess
import pandas as pd
import requests
from datetime import datetime, timezone
import time
import re

# ==============================================================================
# 0. CONFIGURATION
# ==============================================================================
TARGET_REPO = "anni02th/test-spring-petclinic"
TARGET_BRANCH = "main"
# --- IMPORTANT: MAKE SURE THIS IS YOUR REAL TOKEN ---

FEATURE_COLS = [
    'commit_sha', 'commit_date', 'src_churn', 'files_added', 'files_deleted',
    'files_modified', 'test_churn', 'tests_added', 'tests_deleted', 'team_size',
    'sloc', 'test_lines_per_kloc', 'num_commit_comments', 'committers',
    'prev_pass', 'elapsed_days_last_build', 'project_fail_history',
    'project_fail_recent', 'commit_interval', 'project_age'
]

# ==============================================================================
# 1. HELPER FUNCTIONS
# ==============================================================================
def run_command(command, working_dir):
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True, check=True, cwd=working_dir)
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return ""

def make_api_request(endpoint, params=None):
    if not GITHUB_TOKEN or "YOUR_GITHUB" in GITHUB_TOKEN:
        raise ValueError("GITHUB_TOKEN is not set! Please replace the placeholder.")
    
    url = f"https://api.github.com/repos/{TARGET_REPO}/{endpoint}"
    headers = {'Authorization': f'token {GITHUB_TOKEN}'}
    response = None
    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"API request to {url} failed: {e}")
        if response is not None and response.status_code == 403:
            time.sleep(60)
        return None

# ==============================================================================
# 2. FEATURE COLLECTION
# ==============================================================================

def get_code_churn(commit_sha, repo_path):
    features = {'src_churn': 0, 'files_modified': 0, 'test_churn': 0}
    parent_count = len(run_command(f"git rev-list --parents -n 1 {commit_sha}", repo_path).split())
    if parent_count < 2:
        return features

    diff_output = run_command(f"git diff --numstat {commit_sha}~1 {commit_sha}", repo_path)
    if not diff_output:
        return features

    src_insertions, src_deletions, test_insertions, test_deletions = 0, 0, 0, 0
    for line in diff_output.splitlines():
        parts = line.split('\t')
        if len(parts) < 3: continue
        
        if parts[0].isdigit() and parts[1].isdigit():
            insertions, deletions, path = int(parts[0]), int(parts[1]), parts[2]
            if "test" in path.lower():
                test_insertions += insertions
                test_deletions += deletions
            else:
                src_insertions += insertions
                src_deletions += deletions
    
    features['src_churn'] = src_insertions + src_deletions
    features['test_churn'] = test_insertions + test_deletions
    features['files_modified'] = len(diff_output.splitlines())
    return features

# --- NEW: A simple, built-in function to count lines of code ---
def get_sloc_simple(repo_path):
    """
    Calculates Source Lines of Code (SLOC) by manually walking through files.
    This removes the need for any external tools like cloc or pygount.
    """
    features = {'sloc': 0}
    total_code_lines = 0
    # Define file extensions to consider as source code
    source_extensions = {'.java', '.xml', '.properties'}
    
    for root, _, files in os.walk(repo_path):
        # Skip the .git directory
        if '.git' in root:
            continue
            
        for file in files:
            if any(file.endswith(ext) for ext in source_extensions):
                try:
                    with open(os.path.join(root, file), 'r', encoding='utf-8', errors='ignore') as f:
                        lines = f.readlines()
                        # Count non-empty lines that are not single-line comments
                        for line in lines:
                            stripped_line = line.strip()
                            if stripped_line and not stripped_line.startswith(('//', '*', '/*', '#')):
                                total_code_lines += 1
                except Exception:
                    # Ignore files that cannot be read
                    pass
                    
    features['sloc'] = total_code_lines
    return features

# ==============================================================================
# 3. MAIN SCRIPT LOGIC
# ==============================================================================

def main():
    print(f"--- Starting analysis for {TARGET_REPO} ---")
    repo_name = TARGET_REPO.split('/')[-1]
    
    if not os.path.isdir(repo_name):
        print(f"Cloning {TARGET_REPO}...")
        run_command(f"git clone https://github.com/{TARGET_REPO}.git", ".")
    else:
        print(f"Updating {repo_name}...")
        run_command("git pull", repo_name)
    
    print(f"\nFetching all commits for branch '{TARGET_BRANCH}'...")
    all_commits = []
    page = 1
    while True:
        params = {'sha': TARGET_BRANCH, 'per_page': 100, 'page': page}
        commits_page = make_api_request("commits", params=params)
        if not commits_page:
            break
        all_commits.extend(commits_page)
        if len(commits_page) < 100:
            break
        page += 1
    
    all_commits.reverse()
    print(f"Found {len(all_commits)} commits to analyze.")
    if not all_commits:
        return
    
    all_features_list = []
    
    for i, commit in enumerate(all_commits):
        commit_sha = commit['sha']
        commit_date_str = commit['commit']['author']['date']
        commit_date = datetime.fromisoformat(commit_date_str.replace('Z', '+00:00'))
        
        print(f"Processing commit {i+1}/{len(all_commits)}: {commit_sha[:7]}...")
        
        run_command(f"git checkout -q -f {commit_sha}", repo_name)
        
        features = {'commit_sha': commit_sha, 'commit_date': commit_date}
        features.update(get_code_churn(commit_sha, repo_name))
        # --- UPDATED: Call the new, simple SLOC function ---
        features.update(get_sloc_simple(repo_name))
        
        all_features_list.append(features)
        
    df = pd.DataFrame(all_features_list, columns=FEATURE_COLS).fillna(0)
    
    output_filename = f"{repo_name}_historical_data.csv"
    df.to_csv(output_filename, index=False)
    print(f"\n✅ Successfully saved historical data to {output_filename}")

if __name__ == "__main__":
    main()