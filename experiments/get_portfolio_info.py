import os
from collections.abc import Mapping, Sequence
from typing import Any

import pandas as pd
import quantstats as qs
import requests
from dotenv import load_dotenv

load_dotenv()


def fetch_ghostfolio_data() -> (
    tuple[list[dict[str, Any]], list[dict[str, Any]], pd.DataFrame]
):
    """Fetch portfolio performance, activities, and holdings from Ghostfolio.

    Reads API host and API key from environment variables, authenticates
    anonymously, and queries the relevant Ghostfolio endpoints.

    Returns:
        tuple[list, list, pd.DataFrame]:
            - performance chart data entries
            - order activity entries
            - holdings table as a pandas DataFrame
    """
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
    holdings = pd.DataFrame(
        requests.get(f"{api_url}/api/v1/portfolio/holdings", headers=headers)
        .json()
        .get("holdings", [])
    )
    return performance, activities, holdings


def calculate_daily_returns(
    performance_data: Sequence[Mapping[str, Any]] | None,
    activities: Sequence[Mapping[str, Any]] | None,
    frequency: str = "B",
) -> pd.Series:
    """Calculate time-series returns with external cash-flow adjustments.

    Uses a Modified Dietz-style formulation on resampled portfolio values and
    aggregated BUY/SELL cash flows to estimate periodic returns.

    Args:
        performance_data (list[dict]): Portfolio performance chart records.
        activities (list[dict]): Transaction activities from Ghostfolio.
        frequency (str, optional): Pandas resample frequency, defaults to
            business day ("B").

    Returns:
        pd.Series: Periodic returns indexed by date, starting from first
        non-zero cash-flow date when available.
    """
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

        def get_cash_flow(row: pd.Series) -> float:
            """Convert one activity row into signed external cash flow.

            BUY is treated as positive inflow and SELL as negative outflow,
            with fees included in the signed amount.

            Args:
                row (pd.Series): A single activity row.

            Returns:
                float: Signed cash-flow amount in base currency.
            """
            # Calculate actual money in/out including fees
            amount = float(row.get("valueInBaseCurrency"))
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


def print_holdings_info(holdings: pd.DataFrame) -> None:
    """Print a formatted holdings summary and portfolio totals.

    Creates a symbol-level table with allocation, value, and performance,
    sorted by holding value, then prints aggregate totals.

    Args:
        holdings (pd.DataFrame): Holdings payload from Ghostfolio API.
    """
    if holdings.empty:
        print("No holdings data.")
        return

    df = holdings.copy()
    net_performance = df["netPerformance"]
    net_performance_pct = df["netPerformancePercent"]
    net_performance_with_fx = df.get(
        "netPerformanceWithCurrencyEffect", net_performance
    )
    net_performance_pct_with_fx = df.get(
        "netPerformancePercentWithCurrencyEffect", net_performance_pct
    )
    currency_change = net_performance_with_fx - net_performance

    summary = (
        pd.DataFrame(
            {
                "Symbol": df["symbol"],
                "Alloc %": (df["allocationInPercentage"] * 100).map("{:.1f}%".format),
                "Value (TWD)": df["valueInBaseCurrency"].map("{:,.0f}".format),
                "P&L": net_performance_with_fx.map("{:,.0f}".format),
                "P&L %": (net_performance_pct_with_fx * 100).map("{:.1f}%".format),
                "Currency Change": currency_change.map("{:,.0f}".format),
            }
        )
        .sort_values(
            by="Value (TWD)",
            key=lambda x: x.str.replace(",", "").astype(float),
            ascending=False,
        )
        .set_index("Symbol")
    )

    total_value = df["valueInBaseCurrency"].sum()
    total_invested = df["investment"].sum()
    total_pnl_with_fx = net_performance_with_fx.sum()
    total_pnl_pct_with_fx = (
        (total_pnl_with_fx / total_invested * 100) if total_invested else 0
    )
    total_currency_change = total_pnl_with_fx - net_performance.sum()

    pd.set_option("display.width", 120)
    print("\nHOLDINGS")
    print("-" * 60)
    print(summary.to_string())
    print("-" * 60)
    print(f"Total Value   : {total_value:,.0f} TWD")
    print(f"Total Invested: {total_invested:,.0f} TWD")
    print(
        f"Total P&L     : {total_pnl_with_fx:,.0f} TWD "
        f"({total_pnl_pct_with_fx:.1f}%)"
    )
    print(f"Currency Change: {total_currency_change:,.0f} TWD")


if __name__ == "__main__":
    # Fetch data from Ghostfolio API and print holdings info
    perf_data, activity_data, holdings_data = fetch_ghostfolio_data()
    print_holdings_info(holdings_data)

    # Generate Performance Report
    # Focus on active period starting from 2025-06-01
    # Calculate daily returns using the modified Dietz method to account for cash flows
    daily_returns = calculate_daily_returns(perf_data, activity_data)
    filtered_returns = daily_returns[daily_returns.index >= "2025-06-01"]
    if not filtered_returns.empty:
        qs.reports.html(
            filtered_returns,
            benchmark="VT",
            rf=0.04,
            output="portfolio_report.html",
            title="Portfolio Performance",
        )
        print("Success: portfolio_report.html generated.")
    else:
        print("No data available for the selected period.")
