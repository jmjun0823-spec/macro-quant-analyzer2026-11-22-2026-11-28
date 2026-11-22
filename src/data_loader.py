import numpy as np
import pandas as pd
import yfinance as yf
import FinanceDataReader as fdr


def _normalize_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume", "Return", "Log_Return"])
    if isinstance(df.columns, pd.MultiIndex):
        df = df.copy()
        df.columns = df.columns.get_level_values(0)
    df = df.sort_index()
    df = df[~df.index.duplicated(keep="last")]
    df["Close"] = pd.to_numeric(df["Close"], errors="coerce")
    if "Volume" in df.columns:
        df["Volume"] = pd.to_numeric(df["Volume"], errors="coerce")
    df = df.dropna(subset=["Close"])
    df["Return"] = df["Close"].pct_change()
    df["Log_Return"] = np.log(df["Close"] / df["Close"].shift(1))
    return df


def fetch_global_data(cfg: dict) -> dict:
    """Yahoo Finance에서 글로벌 지수, 환율, 금리 최장기 일봉 데이터 수집"""
    data_store = {}
    end_date = cfg["end_date"]
    tickers = cfg["tickers"]
    start_dates = cfg["start_dates"]

    for name, ticker in tickers.items():
        if name in ["SP500", "NASDAQ"]:
            start = start_dates["US_EQUITY"]
        elif name in ["KOSPI", "KOSDAQ"]:
            start = start_dates["KR_EQUITY"]
        else:
            start = start_dates["RATES_FX"]

        raw = yf.download(ticker, start=start, end=end_date, progress=False, auto_adjust=True)
        data_store[name] = _normalize_ohlcv(raw)

    return data_store


def fetch_krx_etf_data(cfg: dict) -> pd.DataFrame:
    """FinanceDataReader를 통해 국내 스타일별 ETF 수정주가 수집"""
    close_dict = {}
    start = cfg["start_dates"]["KRX_ETF"]
    end_date = cfg["end_date"]

    for name, code in cfg["krx_etfs"].items():
        df = fdr.DataReader(code, start=start, end=end_date)
        if df is not None and not df.empty and "Close" in df.columns:
            df = df.sort_index()
            df = df[~df.index.duplicated(keep="last")]
            close_dict[name] = pd.to_numeric(df["Close"], errors="coerce")

    if not close_dict:
        return pd.DataFrame()
    return pd.DataFrame(close_dict).ffill().dropna(how="all")
