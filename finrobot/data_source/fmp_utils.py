import os
import requests
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from ..utils import decorate_all_methods, get_next_weekday

from functools import wraps
from typing import Annotated, List

BASE_URL = "https://financialmodelingprep.com/stable"


def init_fmp_api(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        global fmp_api_key
        if os.environ.get("FMP_API_KEY") is None:
            print("Please set the environment variable FMP_API_KEY to use the FMP API.")
            return None
        else:
            fmp_api_key = os.environ["FMP_API_KEY"]
            print("FMP api key found successfully.")
            return func(*args, **kwargs)

    return wrapper


@decorate_all_methods(init_fmp_api)
class FMPUtils:

    def get_target_price(
        ticker_symbol: Annotated[str, "ticker symbol"],
        date: Annotated[str, "date of the target price, should be 'yyyy-mm-dd'"],
    ) -> str:
        """Get the target price for a given stock on a given date"""
        url = f"{BASE_URL}/analyst-estimates?symbol={ticker_symbol}&period=annual&apikey={fmp_api_key}"

        price_target = "Not Given"
        response = requests.get(url)

        if response.status_code == 200:
            data = response.json()
            est = []

            date = datetime.strptime(date, "%Y-%m-%d")
            for tprice in data:
                tdate_str = tprice.get("date", "")
                if not tdate_str:
                    continue
                tdate = datetime.strptime(tdate_str, "%Y-%m-%d")
                if abs((tdate - date).days) <= 999:
                    if tprice.get("revenueAvg"):
                        est.append(tprice["revenueAvg"])

            if est:
                price_target = f"{np.min(est):,.0f} - {np.max(est):,.0f} (md. {np.median(est):,.0f})"
            else:
                price_target = "N/A"
        else:
            return f"Failed to retrieve data: {response.status_code}"

        return price_target

    def get_sec_report(
        ticker_symbol: Annotated[str, "ticker symbol"],
        fyear: Annotated[
            str,
            "year of the 10-K report, should be 'yyyy' or 'latest'. Default to 'latest'",
        ] = "latest",
    ) -> str:
        """Get the url and filing date of the 10-K report for a given stock and year"""
        url = f"{BASE_URL}/sec-filings?symbol={ticker_symbol}&apikey={fmp_api_key}"

        filing_url = None
        response = requests.get(url)

        if response.status_code == 200:
            data = response.json()
            if not data:
                return "No SEC filings found via FMP. Use SEC API via sec_utils instead."
            if fyear == "latest":
                filing_url = data[0].get("finalLink", data[0].get("link"))
                filing_date = data[0].get("fillingDate", data[0].get("filedAt"))
            else:
                for filing in data:
                    fd = filing.get("fillingDate", filing.get("filedAt", ""))
                    if fd and fd.split("-")[0] == fyear:
                        filing_url = filing.get("finalLink", filing.get("link"))
                        filing_date = fd
                        break

            if filing_url:
                return f"Link: {filing_url}\nFiling Date: {filing_date}"
            return "No matching 10-K filing found."
        else:
            return f"Failed to retrieve data: {response.status_code}"

    def get_historical_market_cap(
        ticker_symbol: Annotated[str, "ticker symbol"],
        date: Annotated[str, "date of the market cap, should be 'yyyy-mm-dd'"],
    ) -> str:
        """Get the historical market capitalization for a given stock on a given date"""
        date = get_next_weekday(date).strftime("%Y-%m-%d")
        url = f"{BASE_URL}/historical-market-capitalization?symbol={ticker_symbol}&limit=5&apikey={fmp_api_key}"

        mkt_cap = None
        response = requests.get(url)

        if response.status_code == 200:
            data = response.json()
            if data:
                target_date = datetime.strptime(date, "%Y-%m-%d")
                closest = None
                min_diff = float("inf")
                for d in data:
                    d_date = datetime.strptime(d["date"], "%Y-%m-%d")
                    diff = abs((target_date - d_date).days)
                    if diff < min_diff:
                        min_diff = diff
                        closest = d
                if closest:
                    return closest["marketCap"]
            return "N/A"
        else:
            return f"Failed to retrieve data: {response.status_code}"

    def get_historical_bvps(
        ticker_symbol: Annotated[str, "ticker symbol"],
        target_date: Annotated[str, "date of the BVPS, should be 'yyyy-mm-dd'"],
    ) -> str:
        """Get the historical book value per share for a given stock on a given date"""
        url = f"{BASE_URL}/ratios?symbol={ticker_symbol}&limit=5&apikey={fmp_api_key}"

        try:
            data = requests.get(url).json()
        except Exception:
            return "No data available"

        if not data:
            return "No data available"

        target_date = datetime.strptime(target_date, "%Y-%m-%d")
        closest = None
        min_diff = float("inf")
        for entry in data:
            entry_date = datetime.strptime(entry["date"], "%Y-%m-%d")
            diff = abs((target_date - entry_date).days)
            if diff < min_diff:
                min_diff = diff
                closest = entry

        if closest and closest.get("bookValuePerShare"):
            return f"{closest['bookValuePerShare']:.2f}"
        return "No BVPS data available"

    def get_financial_metrics(
        ticker_symbol: Annotated[str, "ticker symbol"],
        years: Annotated[int, "number of the years to search from, default to 4"] = 4
    ) -> pd.DataFrame:
        """Get the financial metrics for a given stock for the last 'years' years"""
        df = pd.DataFrame()

        income_url = f"{BASE_URL}/income-statement?symbol={ticker_symbol}&limit={years}&apikey={fmp_api_key}"
        ratios_url = f"{BASE_URL}/ratios?symbol={ticker_symbol}&limit={years}&apikey={fmp_api_key}"
        key_metrics_url = f"{BASE_URL}/key-metrics?symbol={ticker_symbol}&limit={years}&apikey={fmp_api_key}"

        income_data = requests.get(income_url).json()
        key_metrics_data = requests.get(key_metrics_url).json()
        ratios_data = requests.get(ratios_url).json()

        if income_data and key_metrics_data and ratios_data:
            for year_offset in range(min(years, len(income_data), len(key_metrics_data), len(ratios_data))):
                if year_offset == 0:
                    continue
                try:
                    rev = income_data[year_offset]["revenue"]
                    prev_rev = income_data[year_offset - 1]["revenue"]
                    gross = income_data[year_offset]["grossProfit"]
                    ebitda = income_data[year_offset]["ebitda"]
                    net_income = income_data[year_offset]["netIncome"]
                    ev = key_metrics_data[year_offset]["enterpriseValue"]
                    ev_to_ocf = key_metrics_data[year_offset]["evToOperatingCashFlow"]
                    fcf = ev / ev_to_ocf if ev_to_ocf else 0

                    metrics = {
                        "Revenue": round(rev / 1e6),
                        "Revenue Growth": "{}%".format(round(((rev - prev_rev) / prev_rev) * 100, 1)),
                        "Gross Revenue": round(gross / 1e6),
                        "Gross Margin": round((gross / rev), 2),
                        "EBITDA": round(ebitda / 1e6),
                        "EBITDA Margin": round((ebitda / rev), 2),
                        "FCF": round(fcf / 1e6),
                        "FCF Conversion": round((fcf / net_income), 2) if net_income else 0,
                        "ROIC": "{}%".format(round(key_metrics_data[year_offset].get("returnOnInvestedCapital", 0) * 100, 1)),
                        "EV/EBITDA": round(key_metrics_data[year_offset].get("evToEBITDA", 0), 2),
                        "PE Ratio": round(ratios_data[year_offset].get("priceToEarningsRatio", 0), 2),
                        "PB Ratio": round(ratios_data[year_offset].get("priceToBookRatio", 0), 2),
                    }
                    year = income_data[year_offset]["date"][:4]
                    df[year] = pd.Series(metrics)
                except (IndexError, KeyError, ZeroDivisionError):
                    continue

        df = df.sort_index(axis=1)
        return df

    def get_competitor_financial_metrics(
        ticker_symbol: Annotated[str, "ticker symbol"],
        competitors: Annotated[List[str], "list of competitor ticker symbols"],
        years: Annotated[int, "number of the years to search from, default to 4"] = 4
    ) -> dict:
        """Get financial metrics for the company and its competitors."""
        all_data = {}

        symbols = [ticker_symbol] + competitors

        for symbol in symbols:
            income_url = f"{BASE_URL}/income-statement?symbol={symbol}&limit={years}&apikey={fmp_api_key}"
            ratios_url = f"{BASE_URL}/ratios?symbol={symbol}&limit={years}&apikey={fmp_api_key}"
            key_metrics_url = f"{BASE_URL}/key-metrics?symbol={symbol}&limit={years}&apikey={fmp_api_key}"

            income_data = requests.get(income_url).json()
            ratios_data = requests.get(ratios_url).json()
            key_metrics_data = requests.get(key_metrics_url).json()

            metrics = {}

            if income_data and ratios_data and key_metrics_data:
                for year_offset in range(min(years, len(income_data))):
                    try:
                        rev_growth = None
                        if year_offset > 0 and year_offset < len(income_data):
                            prev_rev = income_data[year_offset - 1]["revenue"]
                            if prev_rev:
                                rev_growth = "{}%".format(round(
                                    ((income_data[year_offset]["revenue"] - prev_rev) / prev_rev) * 100, 1
                                ))

                        ev = key_metrics_data[year_offset]["enterpriseValue"]
                        ev_to_ocf = key_metrics_data[year_offset].get("evToOperatingCashFlow", 0)
                        fcf = ev / ev_to_ocf if ev_to_ocf else 0
                        net_income = income_data[year_offset]["netIncome"]

                        metrics[year_offset] = {
                            "Revenue": round(income_data[year_offset]["revenue"] / 1e6),
                            "Revenue Growth": rev_growth,
                            "Gross Margin": round((income_data[year_offset]["grossProfit"] / income_data[year_offset]["revenue"]), 2),
                            "EBITDA Margin": round((income_data[year_offset]["ebitda"] / income_data[year_offset]["revenue"]), 2),
                            "FCF Conversion": round((fcf / net_income), 2) if net_income else None,
                            "ROIC": "{}%".format(round(key_metrics_data[year_offset].get("returnOnInvestedCapital", 0) * 100, 1)),
                            "EV/EBITDA": round(key_metrics_data[year_offset].get("evToEBITDA", 0), 2),
                        }
                    except (IndexError, KeyError, ZeroDivisionError):
                        continue

            df = pd.DataFrame.from_dict(metrics, orient='index')
            df = df.sort_index(axis=1)
            all_data[symbol] = df

        return all_data


if __name__ == "__main__":
    from finrobot.utils import register_keys_from_json

    register_keys_from_json("config_api_keys")
    print(FMPUtils.get_target_price("AAPL", "2026-05-01"))
    print(FMPUtils.get_historical_market_cap("AAPL", "2026-05-01"))
