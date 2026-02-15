import argparse
import io
import zipfile

import pandas as pd
import quantstats as qs
import requests
import statsmodels.api as sm


PORTFOLIO_WEIGHTS: dict[str, float] = {
    "UPRO": 0.05,
    "MIDU": 0.025,
    "SAA": 0.025,
    "00631L.TW": 0.05,
    "EFO": 0.05,
    "RSST": 0.20,
    "AVUV": 0.075,
    "QVAL": 0.075,
    "QMOM": 0.15,
    "AVDV": 0.075,
    "IVAL": 0.075,
    "IMOM": 0.15,
}


def load_ken_french_daily_factors(
    dataset_name: str, columns: list[str]
) -> pd.DataFrame:
    url = f"https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/{dataset_name}_CSV.zip"
    response = requests.get(url, timeout=30)
    response.raise_for_status()

    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        text = archive.read(archive.namelist()[0]).decode("latin-1")

    rows: list[list[str]] = []
    for line in text.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if not parts or not (parts[0].isdigit() and len(parts[0]) == 8):
            continue

        values = parts[1 : 1 + len(columns)]
        if len(values) == len(columns) and all(values):
            rows.append([parts[0], *values])

    if not rows:
        raise ValueError(f"No daily rows found for dataset: {dataset_name}")

    data = pd.DataFrame(rows, columns=["date", *columns])
    data["date"] = pd.to_datetime(data["date"], format="%Y%m%d")
    data = data.set_index("date").sort_index()
    return data.apply(pd.to_numeric, errors="coerce").dropna()


def build_weighted_portfolio_returns(
    portfolio_weights: dict[str, float],
    start_date: pd.Timestamp,
    end_date: pd.Timestamp,
) -> pd.Series:
    series_by_ticker: list[pd.Series] = []
    for ticker, weight in portfolio_weights.items():
        ticker_returns = qs.utils.download_returns(ticker).rename(ticker)
        if ticker_returns.empty:
            raise ValueError(f"No return data found for ticker '{ticker}'")

        ticker_returns.index = pd.to_datetime(ticker_returns.index).tz_localize(None)
        ticker_returns = ticker_returns.loc[
            (ticker_returns.index >= start_date) & (ticker_returns.index <= end_date)
        ]
        if ticker_returns.empty:
            raise ValueError(
                f"No return data for ticker '{ticker}' in selected date range"
            )

        series_by_ticker.append(ticker_returns * weight)

    combined = pd.concat(series_by_ticker, axis=1, join="inner")
    if combined.empty:
        raise ValueError("No overlapping return dates across portfolio tickers")

    return combined.sum(axis=1).rename("portfolio_return")


def build_analysis_data(
    portfolio_returns: pd.Series, start_date: pd.Timestamp, end_date: pd.Timestamp
) -> pd.DataFrame:
    ff3 = load_ken_french_daily_factors(
        "Developed_3_Factors_Daily", ["Mkt-RF", "SMB", "HML", "RF"]
    )
    mom = load_ken_french_daily_factors("Developed_Mom_Factor_Daily", ["Mom"])

    factors = ff3.join(mom, how="inner")
    factors = factors.loc[(factors.index >= start_date) & (factors.index <= end_date)]
    if factors.empty:
        raise ValueError("No factor data available in the requested date range")

    # Portfolio returns are decimals; Ken French factors are percentages.
    portfolio_pct = (portfolio_returns * 100.0).rename("portfolio_return")
    data = pd.concat([portfolio_pct, factors], axis=1, join="inner").dropna()
    if data.empty:
        raise ValueError("No overlapping dates between portfolio returns and factors")

    data["portfolio_excess_return"] = data["portfolio_return"] - data["RF"]
    return data


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run a simple 4-factor regression for a weighted ETF/stock portfolio"
    )
    parser.add_argument(
        "--start-date",
        default="2015-01-01",
        help="Start date for return analysis (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--end-date",
        default=None,
        help="End date for analysis (YYYY-MM-DD). Defaults to latest available date.",
    )
    parser.add_argument(
        "--output-csv",
        default="factor_analysis_dataset.csv",
        help="Where to save merged portfolio/factor dataset",
    )
    parser.add_argument(
        "--summary-txt",
        default="factor_regression_summary.txt",
        help="Where to save statsmodels text summary",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    start_date = pd.Timestamp(args.start_date)

    end_date = (
        pd.Timestamp(args.end_date) if args.end_date is not None else pd.Timestamp.now()
    )
    if end_date < start_date:
        raise ValueError("end-date must be greater than or equal to start-date")

    portfolio_weights = {
        ticker.upper(): float(weight) for ticker, weight in PORTFOLIO_WEIGHTS.items()
    }
    if not portfolio_weights:
        raise ValueError("PORTFOLIO_WEIGHTS cannot be empty")

    total_weight = sum(portfolio_weights.values())
    if total_weight <= 0:
        raise ValueError("PORTFOLIO_WEIGHTS must sum to a positive number")

    if abs(total_weight - 1.0) > 1e-9:
        portfolio_weights = {
            ticker: weight / total_weight
            for ticker, weight in portfolio_weights.items()
        }

    portfolio_returns = build_weighted_portfolio_returns(
        portfolio_weights, start_date, end_date
    )

    analysis_df = build_analysis_data(portfolio_returns, start_date, end_date)

    X = sm.add_constant(analysis_df[["Mkt-RF", "SMB", "HML", "Mom"]])
    y = analysis_df["portfolio_excess_return"]
    result = sm.OLS(y, X).fit()

    coefficients = pd.DataFrame(
        {
            "coef": result.params,
            "std_err": result.bse,
            "t_stat": result.tvalues,
            "p_value": result.pvalues,
        }
    )
    summary_text = result.summary().as_text()

    print("=== 4-Factor Regression (Excess Return) ===")
    print(f"Observations: {int(result.nobs)}")
    print(f"R-squared: {result.rsquared:.4f}")
    print(f"Adj. R-squared: {result.rsquared_adj:.4f}")
    print()
    print(coefficients.round(4).to_string())

    analysis_df.to_csv(args.output_csv, index=True)
    with open(args.summary_txt, "w", encoding="utf-8") as f:
        f.write(summary_text)

    print()
    print(f"Saved merged dataset to: {args.output_csv}")
    print(f"Saved regression summary to: {args.summary_txt}")


if __name__ == "__main__":
    main()
