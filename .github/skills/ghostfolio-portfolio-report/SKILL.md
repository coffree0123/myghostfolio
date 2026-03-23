---
name: ghostfolio-portfolio-report
description: 'Generate and summarize the Ghostfolio portfolio report from experiments/get_portfolio_info.py. Use when you need to run the Ghostfolio reporting script, create experiments/portfolio_report.html, inspect holdings output, and summarize QuantStats performance metrics.'
argument-hint: 'Describe any report customizations, such as benchmark, date filter, or extra metrics to highlight.'
user-invocable: true
---

# Ghostfolio Portfolio Report

## What This Skill Does

This skill runs the Ghostfolio portfolio reporting workflow in this repository and produces a concise summary of the results.

It covers:
- Running the experiment script at `experiments/get_portfolio_info.py`
- Using the repository's expected Python environment: `conda run -n finance python ...`
- Generating `experiments/portfolio_report.html`
- Reading the script's console output for holdings, total value, total invested, and total P&L
- Reading the generated QuantStats HTML report and summarizing the important performance metrics

## When To Use

Use this skill when the user asks to:
- Generate the Ghostfolio portfolio report
- Run the portfolio analysis experiment
- Refresh `portfolio_report.html`
- Summarize the latest portfolio performance report
- Review holdings, drawdown, Sharpe, CAGR, or benchmark comparison from the Ghostfolio report

## Repository-Specific Context

- Script path: `experiments/get_portfolio_info.py`
- Output report: `experiments/portfolio_report.html`
- Environment variables are loaded from `experiments/.env`
- Expected execution environment for experiments in this repo: `conda run -n finance python ...`
- Ghostfolio API is expected to be reachable through the host configured by `GHOSTFOLIO_API_HOST`

## Procedure

1. Read `experiments/get_portfolio_info.py` to confirm:
   - required environment variables
   - output file path
   - benchmark, date filtering, and any report assumptions
2. Check whether the configured Python environment is suitable.
   - If the default interpreter is missing packages like `pandas`, `quantstats`, or `requests`, use the repo-preferred command: `conda run -n finance python experiments/get_portfolio_info.py`
3. Run the script from the `experiments` directory so local `.env` loading behaves as expected.
4. Capture the console output and extract:
   - holdings table
   - total value
   - total invested
   - total P&L and percentage
   - strongest and weakest positions by P&L or allocation, if useful
5. Confirm that `experiments/portfolio_report.html` was generated.
6. Read the generated HTML report and extract the key QuantStats metrics.
   Focus on:
   - report date range
   - benchmark
   - cumulative return
   - CAGR
   - Sharpe
   - Sortino
   - max drawdown
   - annualized volatility
   - Calmar
   - recent performance windows such as MTD, 3M, 6M, YTD, and 1Y
7. Summarize the result for the user in plain language.
   Include:
   - whether the report was successfully generated
   - a concise holdings summary
   - the most important performance metrics
   - a short interpretation of relative performance versus the benchmark

## Decision Points

- If the script fails because the default Python interpreter is missing dependencies, switch to `conda run -n finance python ...` rather than editing the script.
- If the script fails because the Ghostfolio API is unavailable, report that the workflow is blocked by the backend connection or credentials.
- If the HTML report is generated but metrics are hard to find, search the report for table entries such as `CAGR`, `Sharpe`, `Sortino`, `Max Drawdown`, `Volatility`, `MTD`, and `YTD`.
- If the user asks for a deeper explanation, add interpretation of benchmark underperformance, volatility tradeoffs, and recent drawdown context.

## Completion Criteria

The task is complete when all of the following are true:
- The script has been executed successfully, or the blocker is clearly identified
- `experiments/portfolio_report.html` exists and reflects the latest run
- The holdings summary has been captured from console output
- The major report metrics have been extracted from the HTML report
- The user receives a concise summary with both raw numbers and interpretation

## Example Prompts

- `/ghostfolio-portfolio-report Generate the latest portfolio report and summarize it.`
- `/ghostfolio-portfolio-report Re-run the Ghostfolio report using the current .env and compare it to VT.`
- `/ghostfolio-portfolio-report Refresh portfolio_report.html and give me the key risk and return metrics.`
- `/ghostfolio-portfolio-report Run the experiment and highlight the top contributors and current drawdown.`