import os
import pandas as pd
import numpy as np
from dotenv import load_dotenv
import requests

load_dotenv()

def get_ghostfolio_performance_raw_data(url, security_token):
    # 1. Get JWT token
    auth_resp = requests.post(f"{url}/api/v1/auth/anonymous", json={"accessToken": security_token})
    auth_resp.raise_for_status()
    jwt_token = auth_resp.json()["authToken"]

    # 2. Retrieve performance data
    headers = {"Authorization": f"Bearer {jwt_token}"}
    perf_resp = requests.get(f"{url}/api/v2/portfolio/performance?range=max", headers=headers)
    perf_resp.raise_for_status()
    
    return perf_resp.json().get("chart", [])

def get_ghostfolio_activities_raw_data(url, security_token):
    # 1. Get JWT token
    auth_resp = requests.post(f"{url}/api/v1/auth/anonymous", json={"accessToken": security_token})
    auth_resp.raise_for_status()
    jwt_token = auth_resp.json()["authToken"]
    
    # 2. Retrieve activities
    headers = {
        "Authorization": f"Bearer {jwt_token}",
        "Content-Type": "application/json"
    }
    response = requests.get(f"{url}/api/v1/order", headers=headers)
    response.raise_for_status()
    activities = response.json().get('activities', [])

    return activities

def calculate_twr_daily_returns(performance_data, activities_data):
    # 1. Prepare Performance Data
    df_perf = pd.DataFrame(performance_data)
    df_perf['date'] = pd.to_datetime(df_perf['date']).dt.date
    # Keep only necessary columns and sort by date
    df_perf = df_perf[['date', 'netWorth']].sort_values('date')

    # 2. Prepare Activities Data (Inflows)
    df_act = pd.DataFrame(activities_data)
    df_act['date'] = pd.to_datetime(df_act['date']).dt.date
    
    # Calculate net cash flow: BUYs are positive, SELLs are negative
    df_act['net_inflow'] = df_act.apply(
        lambda x: x['valueInBaseCurrency'] if x['type'] == 'BUY' else 
                 (-x['valueInBaseCurrency'] if x['type'] == 'SELL' else 0), axis=1
    )
    
    # Group by date to handle multiple trades in a single day
    df_daily_inflow = df_act.groupby('date')['net_inflow'].sum().reset_index()

    # 3. Merge Datasets
    # Join activity data onto the daily performance timeline
    df = pd.merge(df_perf, df_daily_inflow, on='date', how='left').fillna(0)

    # 4. Calculate Daily Return (Time-Weighted)
    # Formula: (Today's Value - Today's Inflow) / Yesterday's Value - 1
    df['prev_worth'] = df['netWorth'].shift(1)
    df['daily_return'] = (df['netWorth'] - df['net_inflow']) / df['prev_worth'] - 1

    # 5. Clean Data
    # Fill the first day or any invalid calculation with 0
    df['daily_return'] = df['daily_return'].replace([np.inf, -np.inf], np.nan).fillna(0)

    # Return as a simple list of dictionaries
    return df[['date', 'daily_return']].to_dict('records')

# Example usage
if __name__ == "__main__":
    api_host = os.getenv("GHOSTFOLIO_API_HOST")
    api_key = os.getenv("GHOSTFOLIO_API_KEY")
    performance_data = get_ghostfolio_performance_raw_data(api_host, api_key)
    activity_data = get_ghostfolio_activities_raw_data(api_host, api_key)
    
    daily_returns_list = calculate_twr_daily_returns(performance_data, activity_data)
    returns = [x['daily_return'] for x in daily_returns_list]
    # 1. Clean the data (already did returns[3:])
    returns = np.array(returns[3:])

    # 2. Calculate Daily Metrics
    avg_daily_return = np.mean(returns)
    std_daily_return = np.std(returns)

    # 3. Annualize the Metrics (using 365 days)
    # Annual Return = Mean Daily Return * 365
    avg_return_annualized = avg_daily_return * 365
    
    # Annual Volatility = Daily Std Dev * Square Root of 365
    std_dev_annualized = std_daily_return * np.sqrt(365)

    # 4. Calculate Sharpe Ratio (Risk-free rate = 4%)
    rf_rate = 0.04
    sharpe = (avg_return_annualized - rf_rate) / std_dev_annualized

    # 5. Display Results
    print(f"--- Portfolio Performance Metrics ---")
    print(f"Average Annual Return: {avg_return_annualized:.2%}")
    print(f"Annual Volatility:     {std_dev_annualized:.2%}")
    print(f"Sharpe Ratio:          {sharpe:.2f}")