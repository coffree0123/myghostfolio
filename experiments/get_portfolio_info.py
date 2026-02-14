import os
import pandas as pd
import quantstats as qs
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

def calculate_twr_daily_returns(performance_data):
    """
    Transforms Ghostfolio performance data into a daily return series 
    optimized for QuantStats by aligning to a Business Day calendar.
    """
    if not performance_data:
        return pd.Series(dtype=float)

    # 1. Load data into DataFrame
    df = pd.DataFrame(performance_data)
    
    # 2. Convert date column and set as index (required for resampling)
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date').set_index('date')
    
    # 3. Calculate Daily Returns from Cumulative Performance
    # Formula: r(t) = (1 + Cumulative_Ret_Today) / (1 + Cumulative_Ret_Yesterday) - 1
    # We use 'netPerformanceInPercentageWithCurrencyEffect' as it accounts for TWR.
    cum_ret = df['netPerformanceInPercentageWithCurrencyEffect']
    daily_returns = (1 + cum_ret) / (1 + cum_ret.shift(1)) - 1
    
    # 4. Handle the initial data point
    # The first row will be NaN after shift; we set it to 0 to establish a starting point.
    daily_returns.iloc[0] = 0
    
    # 5. Resample to Business Days ('B')
    # This automatically removes Saturdays and Sundays. 
    # .asfreq() ensures that if a weekday is missing in the data, it is created as NaN.
    daily_series = daily_returns.resample('B').asfreq()
    
    # 6. Fill missing values
    # We fill NaNs with 0.0 (meaning 0% return) to handle market holidays 
    # and ensure the timeline is continuous for Volatility calculations.
    daily_series = daily_series.fillna(0.0)
    
    # 7. Clean up the start of the series
    # Optional: Remove the leading zeros before your first actual investment 
    # to avoid skewing "Time Under Water" or "Max Drawdown" duration metrics.
    first_valid_date = daily_series[daily_series != 0].index.min()
    if pd.notna(first_valid_date):
        daily_series = daily_series[first_valid_date:]

    return daily_series.astype(float)

def analyze_with_quantstats(daily_returns_series):
    # Generate a comprehensive HTML report using QuantStats
    qs.reports.html(daily_returns_series, output='portfolio_report.html', title='My Portfolio', benchmark="VT", rf=0.04)

# Example usage
if __name__ == "__main__":
    api_host = os.getenv("GHOSTFOLIO_API_HOST")
    api_key = os.getenv("GHOSTFOLIO_API_KEY")
    performance_data = get_ghostfolio_performance_raw_data(api_host, api_key)
    # If you want to analyze activities, uncomment the following line and ensure you have the correct permissions and data structure
    # activity_data = get_ghostfolio_activities_raw_data(api_host, api_key)

    daily_returns_series = calculate_twr_daily_returns(performance_data)
    # Remove the first few entries to mitigate the impact of the initial value and any potential outliers at the start of the series
    clean_daily_returns = daily_returns_series.iloc[2:]

    # Start to analyze the cleaned daily returns with QuantStats
    # My work start from June 2025, so I want to focus on the performance from that point onward 
    # to get a more accurate picture of the portfolio's behavior during my active management period.
    start_date = '2025-06-01'
    real_daily_returns = clean_daily_returns[clean_daily_returns.index >= start_date]
    analyze_with_quantstats(real_daily_returns)