# predict.py
import os
import subprocess
import pandas as pd

def run_command(command):
    """Helper function to run a shell command and return its output."""
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"Command failed: {e}")
        return ""

def collect_features():
    """Gathers features from the live Git repo."""
    features = {}

    # Example: Get the number of modified files.
    files_changed_str = run_command("git diff --name-only HEAD~1 HEAD | wc -l")
    features['files_modified'] = int(files_changed_str) if files_changed_str else 0

    # --- Add your other feature collection logic here ---
    # (e.g., parse git diff, run cloc, call GitHub API, etc.)
    features['src_churn'] = 0 # Placeholder
    features['team_size'] = 0 # Placeholder
    features['sloc'] = 0      # Placeholder

    print(f"Collected Features: {features}")
    return features

# --- Main execution block ---
if __name__ == "__main__":
    # Get the commit hash from the environment variable
    commit_hash = os.environ.get('GITHUB_SHA', 'unknown_commit')
    
    # Collect the features from the repository
    local_features = collect_features()
    
    # Create a DataFrame and save the features to a CSV file
    df_test = pd.DataFrame([local_features])
    csv_filename = f"test_data_{commit_hash[:7]}.csv"
    df_test.to_csv(csv_filename, index=False)
    
    print(f"Successfully saved test data to {csv_filename}")