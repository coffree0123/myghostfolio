import os
import pandas as pd
import quantstats as qs
import requests
from dotenv import load_dotenv

load_dotenv()


def fetch_ghostfolio_data():
    api_url = os.getenv("GHOSTFOLIO_API_HOST")
    api_token = os.getenv("GHOSTFOLIO_API_KEY")

    # Authenticate and get headers
    auth_resp = requests.post(
        f"{api_url}/api/v1/auth/anonymous", json={"accessToken": api_token}
    ).json()
    headers = {"Authorization": f"Bearer {auth_resp['authToken']}"}

    # Fetch performance chart and activity history
    performance = (
        requests.get(
            f"{api_url}/api/v2/portfolio/performance?range=max", headers=headers
        )
        .json()
        .get("chart", [])
    )
    activities = (
        requests.get(f"{api_url}/api/v1/order", headers=headers)
        .json()
        .get("activities", [])
    )
    return performance, activities


def calculate_daily_returns(performance_data, activities, frequency="B"):
    if not performance_data:
        return pd.Series(dtype=float)

    # 1. Process Daily Net Worth (V_t)
    df_perf = pd.DataFrame(performance_data).assign(
        date=lambda x: pd.to_datetime(x.date).dt.tz_localize(None)
    )
    daily_value = (
        df_perf.set_index("date")["netWorth"].resample(frequency).last().ffill()
    )

    # 2. Process External Cash Flow (CF_t)
    df_activities = pd.DataFrame(activities or [])
    if not df_activities.empty:
        df_activities["date"] = pd.to_datetime(df_activities["date"]).dt.tz_localize(
            None
        )

        # Filter out activities from excluded accounts
        is_active = df_activities["account"].apply(
            lambda a: not a.get("isExcluded", False) if isinstance(a, dict) else True
        )
        df_activities = df_activities[is_active]

        def get_cash_flow(row):
            # Calculate actual money in/out including fees
            amount = float(
                row.get("valueInBaseCurrency")
                or (float(row["quantity"]) * float(row["unitPrice"]))
            )
            fee = float(row.get("feeInBaseCurrency", 0))
            # BUY is positive inflow, SELL is negative outflow (consumption)
            return (
                (amount + fee)
                if row["type"] == "BUY"
                else -(amount - fee) if row["type"] == "SELL" else 0
            )

        cash_flows = df_activities.assign(
            flow=df_activities.apply(get_cash_flow, axis=1)
        )
        daily_cash_flow = cash_flows.set_index("date")["flow"].resample(frequency).sum()
    else:
        daily_cash_flow = pd.Series(0.0, index=daily_value.index)

    # 3. Modified Dietz Formula: (V_t - V_(t-1) - CF_t) / (V_(t-1) + 0.5 * CF_t)
    df_combined = pd.DataFrame(
        {"value": daily_value, "cash_flow": daily_cash_flow}
    ).fillna(0)
    prev_value = df_combined["value"].shift(1)
    denominator = prev_value + 0.5 * df_combined["cash_flow"]

    returns = (
        df_combined["value"] - prev_value - df_combined["cash_flow"]
    ) / denominator
    returns = returns.replace([float("inf"), -float("inf")], 0).fillna(0)
    returns[denominator <= 0] = 0

    # Start analysis from the first investment date
    first_date = daily_cash_flow[daily_cash_flow != 0].index.min()
    start_point = first_date if pd.notna(first_date) else returns.index[0]
    return returns[returns.index >= start_point]


if __name__ == "__main__":
    perf_data, activity_data = fetch_ghostfolio_data()
    daily_returns = calculate_daily_returns(perf_data, activity_data)

    # Generate Performance Report
    # Focus on active period starting from 2025-06-01
    filtered_returns = daily_returns[daily_returns.index >= "2025-06-01"]
    if not filtered_returns.empty:
        qs.reports.html(
            filtered_returns,
            benchmark="VT",
            output="portfolio_report.html",
            title="Portfolio Performance",
        )
        print("Success: portfolio_report.html generated.")
    else:
        print("No data available for the selected period.")
