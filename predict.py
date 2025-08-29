# predict.py
import os
import subprocess
import requests
import json
import pandas as pd # Make sure pandas is in your requirements.txt

# ... (keep your collect_features and get_prediction_from_api functions) ...

# --- 3. Main execution ---
if __name__ == "__main__":
    # Get the commit hash from environment variables provided by GitHub Actions
    commit_hash = os.environ.get('7abc1a7ecc689ee070d16ab5804fdfca7e466eaa', 'changes')
    
    # 1. Collect features from the live repo
    local_features = collect_features()
    
    # 2. Save the collected features to a CSV file
    # Create a DataFrame from the dictionary of features
    df_test = pd.DataFrame([local_features]) 
    
    # Define a unique filename for the test data
    csv_filename = f"test_data_{commit_hash[:7]}.csv" 
    
    # Save the DataFrame to a CSV file
    df_test.to_csv(csv_filename, index=False)
    print(f"Successfully saved test data to {csv_filename}")

    # 3. Call your API to get the prediction (this part remains the same)
    final_prediction = get_prediction_from_api(local_features)
    
    # This print statement is what the GitHub Action captures for the prediction output
    print(final_prediction)