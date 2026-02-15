import os
import pandas as pd
import quantstats as qs
from dotenv import load_dotenv
import requests

load_dotenv()


def get_ghostfolio_performance_raw_data(url, security_token):
    # 1. Get JWT token
    auth_resp = requests.post(
        f"{url}/api/v1/auth/anonymous", json={"accessToken": security_token}
    )
    auth_resp.raise_for_status()
    jwt_token = auth_resp.json()["authToken"]

    # 2. Retrieve performance data
    headers = {"Authorization": f"Bearer {jwt_token}"}
    perf_resp = requests.get(
        f"{url}/api/v2/portfolio/performance?range=max", headers=headers
    )
    perf_resp.raise_for_status()

    return perf_resp.json().get("chart", [])


def get_ghostfolio_activities_raw_data(url, security_token):
    # 1. Get JWT token
    auth_resp = requests.post(
        f"{url}/api/v1/auth/anonymous", json={"accessToken": security_token}
    )
    auth_resp.raise_for_status()
    jwt_token = auth_resp.json()["authToken"]

    # 2. Retrieve activities
    headers = {
        "Authorization": f"Bearer {jwt_token}",
        "Content-Type": "application/json",
    }
    response = requests.get(f"{url}/api/v1/order", headers=headers)
    response.raise_for_status()
    activities = response.json().get("activities", [])

    return activities


def calculate_twr_daily_returns(performance_data, frequency="D"):
    """
    Transforms Ghostfolio cumulative performance into a return series for
    QuantStats.

    frequency:
        - "D": calendar days (best for crypto/mixed portfolios)
        - "B": business days (best for stock-only comparisons/benchmarks)
    """
    if not performance_data:
        return pd.Series(dtype=float)

    frequency = frequency.upper()
    if frequency not in {"D", "B"}:
        raise ValueError("frequency must be 'D' (calendar) or 'B' (business day)")

    # 1. Load data into DataFrame
    df = pd.DataFrame(performance_data)

    # 2. Convert date column and set as index (required for resampling)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").set_index("date")

    # 3. Build a continuous cumulative return series on the requested frequency
    # Ghostfolio values are return ratios (e.g. 0.12 = +12%), not percent points.
    cum_ret = df["netPerformanceInPercentageWithCurrencyEffect"].astype(float)
    cum_ret_daily = cum_ret.resample(frequency).ffill()

    # 4. Convert cumulative returns into daily returns
    # Formula: r(t) = (1 + Cumulative_t) / (1 + Cumulative_t-1) - 1
    daily_series = (1 + cum_ret_daily) / (1 + cum_ret_daily.shift(1)) - 1

    # 5. Handle the initial data point
    daily_series.iloc[0] = 0.0

    # 6. Clean up the start of the series
    # Optional: Remove the leading zeros before your first actual investment
    # to avoid skewing "Time Under Water" or "Max Drawdown" duration metrics.
    first_valid_date = daily_series[daily_series != 0].index.min()
    if pd.notna(first_valid_date):
        daily_series = daily_series[first_valid_date:]

    return daily_series.astype(float)


def analyze_with_quantstats(daily_returns_series, benchmark="VT"):
    # Generate a comprehensive HTML report using QuantStats
    qs.reports.html(
        daily_returns_series,
        output="portfolio_report.html",
        title="My Portfolio",
        benchmark=benchmark,
        rf=0.04,
    )


# Example usage
if __name__ == "__main__":
    api_host = os.getenv("GHOSTFOLIO_API_HOST")
    api_key = os.getenv("GHOSTFOLIO_API_KEY")
    performance_data = get_ghostfolio_performance_raw_data(api_host, api_key)
    # If you want to analyze activities, uncomment the following line and ensure you have the correct permissions and data structure
    # activity_data = get_ghostfolio_activities_raw_data(api_host, api_key)

    # For stock-only strategy comparison against VT, use business-day frequency.
    daily_returns_series = calculate_twr_daily_returns(performance_data, frequency="B")
    # Start to analyze the cleaned daily returns with QuantStats
    # My work start from June 2025, so I want to focus on the performance from that point onward
    # to get a more accurate picture of the portfolio's behavior during my active management period.
    start_date = "2025-06-01"
    real_daily_returns = daily_returns_series[daily_returns_series.index >= start_date]
    analyze_with_quantstats(real_daily_returns, benchmark="VT")
