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


def calculate_daily_returns(
    performance_data,
    frequency="B",
    value_column="netWorth",
    investment_column="totalInvestmentValueWithCurrencyEffect",
):
    """
    Build a cash-flow-adjusted daily return series from Ghostfolio chart data.

    This is a daily Modified Dietz approximation that is much closer to a
    true strategy-vs-benchmark comparison than deriving returns from ROAI.

    Formula per day:
        r_t = (V_t - V_(t-1) - CF_t) / (V_(t-1) + 0.5 * CF_t)

    where:
        - V_t  = end-of-day portfolio value
        - CF_t = external net cash flow during day t, approximated as the
                 day-over-day change of cumulative invested capital.
    """
    if not performance_data:
        return pd.Series(dtype=float)

    frequency = frequency.upper()
    if frequency not in {"D", "B"}:
        raise ValueError("frequency must be 'D' (calendar) or 'B' (business day)")

    df = pd.DataFrame(performance_data)
    required_columns = {"date", value_column, investment_column}
    missing = required_columns.difference(df.columns)
    if missing:
        raise ValueError(
            f"Missing required column(s) in performance data: {sorted(missing)}"
        )

    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").set_index("date")

    value = df[value_column].astype(float).resample(frequency).ffill()
    cumulative_investment = (
        df[investment_column].astype(float).resample(frequency).ffill().fillna(0.0)
    )

    cash_flow = cumulative_investment.diff().fillna(0.0)

    previous_value = value.shift(1)
    denominator = previous_value + 0.5 * cash_flow
    numerator = value - previous_value - cash_flow

    returns = numerator / denominator

    invalid_denominator = denominator <= 0
    returns[invalid_denominator] = 0.0

    returns = returns.replace([float("inf"), float("-inf")], 0.0).fillna(0.0)

    # Start analysis when invested capital is positive.
    first_invested_date = cumulative_investment[cumulative_investment > 0].index.min()
    if pd.notna(first_invested_date):
        returns = returns[returns.index >= first_invested_date]

    return returns.astype(float)


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

    if not api_host or not api_key:
        raise ValueError("Please set GHOSTFOLIO_API_HOST and GHOSTFOLIO_API_KEY")

    performance_data = get_ghostfolio_performance_raw_data(api_host, api_key)

    # Daily returns for benchmark comparison (cash-flow-adjusted).
    daily_returns_series = calculate_daily_returns(
        performance_data,
        frequency="B",
    )

    # Focus on your active management period.
    start_date = "2025-06-01"
    real_daily_returns = daily_returns_series[daily_returns_series.index >= start_date]

    analyze_with_quantstats(real_daily_returns, benchmark="VT")
