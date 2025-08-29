import os
import subprocess
import pandas as pd
import json
import re
import requests
from datetime import datetime, timezone

# ==============================================================================
# 1. HELPER FUNCTIONS
# ==============================================================================

def run_command(command):
    """Runs a shell command and returns its output."""
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"Command failed: {e.stdout} {e.stderr}")
        return ""

def make_api_request(endpoint):
    """Makes an authenticated request to the GitHub API."""
    token = os.environ.get('GITHUB_TOKEN')
    repo = os.environ.get('GITHUB_REPOSITORY')
    if not token or not repo:
        return None
    
    url = f"https://api.github.com/repos/{repo}/{endpoint}"
    headers = {'Authorization': f'token {token}'}
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"API request to {url} failed: {e}")
        return None

# ==============================================================================
# 2. FEATURE COLLECTION FUNCTIONS
# ==============================================================================

def get_code_churn():
    """Calculates detailed code and test churn from git diff."""
    features = {
        'src_churn': 0, 'files_added': 0, 'files_deleted': 0, 'files_modified': 0,
        'test_churn': 0, 'tests_added': 0, 'tests_deleted': 0
    }
    # --numstat provides per-file stats: insertions, deletions, path
    diff_output = run_command("git diff --numstat HEAD~1 HEAD")
    if not diff_output:
        return features

    src_insertions, src_deletions = 0, 0
    test_insertions, test_deletions = 0, 0
    
    for line in diff_output.splitlines():
        parts = line.split('\t')
        if len(parts) < 3: continue
        
        insertions = int(parts[0])
        deletions = int(parts[1])
        path = parts[2]

        if "test" in path.lower():
            test_insertions += insertions
            test_deletions += deletions
        else:
            src_insertions += insertions
            src_deletions += deletions
            
    features['src_churn'] = src_insertions + src_deletions
    features['test_churn'] = test_insertions + test_deletions
    # Note: This is a simplified file count. A more robust solution would
    # check file status (A, D, M) from `git diff --name-status`.
    features['files_modified'] = len(diff_output.splitlines())
    return features

def get_sloc_and_test_lines():
    """Calculates SLOC for source and test files using cloc."""
    features = {'sloc': 0, 'test_lines_per_kloc': 0}
    # Run cloc on the whole repo and get JSON output
    cloc_json_str = run_command("cloc . --json")
    if not cloc_json_str:
        return features
        
    try:
        cloc_data = json.loads(cloc_json_str)
        # Exclude summary and header keys
        lang_stats = {k: v for k, v in cloc_data.items() if k not in ['header', 'SUM']}
        
        total_code_lines = 0
        test_code_lines = 0

        # Heuristic: Identify test lines by language or common test frameworks
        # This is a simplification; a real implementation would be more robust.
        for lang, stats in lang_stats.items():
            if lang.lower() in ["junit", "testng", "unittest"]:
                 test_code_lines += stats.get('code', 0)
            else:
                 total_code_lines += stats.get('code', 0)
        
        features['sloc'] = total_code_lines
        if total_code_lines > 0:
            features['test_lines_per_kloc'] = (test_code_lines / total_code_lines) * 1000

    except (json.JSONDecodeError, KeyError):
        print("Failed to parse cloc JSON for SLOC.")
    return features
    
def get_commit_metadata():
    """Gets metadata about the specific commit."""
    features = {'num_commit_comments': 0, 'committers': 1}
    commit_sha = os.environ.get('GITHUB_SHA')
    data = make_api_request(f"commits/{commit_sha}")
    if data:
        features['num_commit_comments'] = data.get('commit', {}).get('comment_count', 0)
        # 'committers' in TravisTorrent often meant unique authors over time.
        # Here we simplify to the number of authors for THIS commit (usually 1).
        features['committers'] = 1 if data.get('author') else 0
    return features

def get_project_history():
    """Calculates features based on the project's build and commit history."""
    features = {
        'prev_pass': 1, 'elapsed_days_last_build': 0, 'project_fail_history': 0.0,
        'project_fail_recent': 0.0, 'commit_interval': 0.0, 'project_age': 0
    }
    branch = os.environ.get('GITHUB_REF_NAME')
    
    # 1. Project Age
    repo_data = make_api_request("")
    if repo_data and 'created_at' in repo_data:
        created_at = datetime.fromisoformat(repo_data['created_at'].replace('Z', '+00:00'))
        features['project_age'] = (datetime.now(timezone.utc) - created_at).days
        
    # 2. Build History
    runs_data = make_api_request(f"actions/runs?branch={branch}&per_page=10")
    if runs_data and runs_data.get('workflow_runs'):
        # Filter out the current, in-progress run
        completed_runs = [r for r in runs_data['workflow_runs'] if r['status'] == 'completed']
        if completed_runs:
            # Previous Build features
            last_run = completed_runs[0]
            features['prev_pass'] = 1 if last_run['conclusion'] == 'success' else 0
            last_run_time = datetime.fromisoformat(last_run['created_at'].replace('Z', '+00:00'))
            features['elapsed_days_last_build'] = (datetime.now(timezone.utc) - last_run_time).days

            # History features
            outcomes = [1 if r['conclusion'] == 'success' else 0 for r in completed_runs]
            if outcomes:
                features['project_fail_history'] = 1 - (sum(outcomes) / len(outcomes))
                # Recent history (last 5)
                recent_outcomes = outcomes[:5]
                features['project_fail_recent'] = 1 - (sum(recent_outcomes) / len(recent_outcomes))

    # 3. Commit Interval
    commits_data = make_api_request(f"commits?sha={branch}&per_page=2")
    if commits_data and len(commits_data) > 1:
        time_now = datetime.fromisoformat(commits_data[0]['commit']['author']['date'].replace('Z', '+00:00'))
        time_prev = datetime.fromisoformat(commits_data[1]['commit']['author']['date'].replace('Z', '+00:00'))
        features['commit_interval'] = (time_now - time_prev).total_seconds() / 3600 # in hours

    return features

# ==============================================================================
# 3. MAIN EXECUTION
# ==============================================================================

if __name__ == "__main__":
    # Initialize a dictionary to hold all feature data
    all_features = {}
    
    # Run each collection function and merge the results
    all_features.update(get_code_churn())
    all_features.update(get_sloc_and_test_lines())
    all_features.update(get_commit_metadata())
    all_features.update(get_project_history())
    
    # Use a predefined list of columns to ensure order and completeness
    feature_cols = [
        'src_churn', 'files_added', 'files_deleted', 'files_modified',
        'test_churn', 'tests_added', 'tests_deleted', 'team_size', 'sloc',
        'test_lines_per_kloc', 'num_commit_comments', 'committers', 'prev_pass',
        'elapsed_days_last_build', 'project_fail_history', 'project_fail_recent',
        'commit_interval', 'project_age'
    ]
    
    # Create a DataFrame with the defined columns, filling missing values with 0
    df = pd.DataFrame([all_features], columns=feature_cols).fillna(0)
    
    # Save the final CSV
    commit_hash = os.environ.get('GITHUB_SHA', 'unknown_commit')
    csv_filename = f"test_data_{commit_hash[:7]}.csv"
    df.to_csv(csv_filename, index=False)
    
    print(f"Successfully collected all features and saved to {csv_filename}")
    print("Collected data:")
    print(df.to_string())