import os
import subprocess
import pandas as pd
import json
import re
import requests

def run_command(command):
    """Helper function to run a shell command and return its output."""
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"Command failed: {e}")
        return ""

def get_code_churn():
    """Calculates code churn by parsing git diff output."""
    churn_data = {'files_modified': 0, 'src_churn': 0}
    # Use --shortstat to get a summary of changes
    diff_output = run_command("git diff --shortstat HEAD~1 HEAD")
    if not diff_output:
        return churn_data

    # Regex to find "X files changed, Y insertions(+), Z deletions(-)"
    match = re.search(r'(\d+)\s*file[s]? changed(?:, (\d+)\s*insertion[s]?\(\+\))?(?:, (\d+)\s*deletion[s]?\(-\))?', diff_output)
    if match:
        churn_data['files_modified'] = int(match.group(1) or 0)
        insertions = int(match.group(2) or 0)
        deletions = int(match.group(3) or 0)
        churn_data['src_churn'] = insertions + deletions
    return churn_data

def get_sloc():
    """Calculates Source Lines of Code (SLOC) using the cloc tool."""
    sloc_data = {'sloc': 0}
    # Run cloc and get the output in JSON format
    cloc_json_str = run_command("cloc . --json")
    if not cloc_json_str:
        return sloc_data
    
    try:
        cloc_data = json.loads(cloc_json_str)
        # We are interested in the total lines of code from the summary
        if 'SUM' in cloc_data and 'code' in cloc_data['SUM']:
            sloc_data['sloc'] = cloc_data['SUM']['code']
    except json.JSONDecodeError:
        print("Failed to parse cloc JSON output.")
    return sloc_data

def get_team_size():
    """Gets the number of contributors from the GitHub API."""
    team_data = {'team_size': 0}
    token = os.environ.get('GITHUB_TOKEN')
    repo = os.environ.get('GITHUB_REPOSITORY')

    if not token or not repo:
        print("GitHub token or repository not found in environment variables.")
        return team_data

    # Call the GitHub API's contributors endpoint
    url = f"https://api.github.com/repos/{repo}/contributors?per_page=100"
    headers = {'Authorization': f'token {token}'}
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        contributors = response.json()
        team_data['team_size'] = len(contributors)
    except requests.exceptions.RequestException as e:
        print(f"Failed to get team size from GitHub API: {e}")
    return team_data

def collect_features():
    """Gathers all features from the live Git repo."""
    # Start with a base dictionary
    features = {}

    # Get data from each source and update the dictionary
    features.update(get_code_churn())
    features.update(get_sloc())
    features.update(get_team_size())
    
    print(f"Collected Features: {features}")
    return features

# --- Main execution block ---
if __name__ == "__main__":
    commit_hash = os.environ.get('GITHUB_SHA', 'unknown_commit')
    local_features = collect_features()
    
    df_test = pd.DataFrame([local_features])
    csv_filename = f"test_data_{commit_hash[:7]}.csv"
    df_test.to_csv(csv_filename, index=False)
    
    print(f"Successfully saved test data to {csv_filename}")