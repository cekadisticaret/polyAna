"""Freqtrade SampleStrategy TA → saatlik Polymarket UP/DOWN sinyali (1h mum)."""
from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass

import numpy as np
import pandas as pd
import talib.abstract as ta
from technical import qtpylib

# SampleStrategy varsayılanları (user_data/strategies/sample_strategy.py)
BUY_RSI = 30
SHORT_RSI = 70


@dataclass
class FreqtradePmSignal:
    symbol: str
    predicted_dir: str
    current_price: float
    rsi: float
    macd_bull: bool
    tema_rising: bool
    long_bias: bool
    short_bias: bool
    prob_up: float
    prob_down: float
    trend: str


def _fetch_klines(symbol: str, limit: int = 120) -> pd.DataFrame:
    url = (
        f"https://fapi.binance.com/fapi/v1/klines?"
        f"symbol={symbol}&interval=1h&limit={limit}"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        raw = json.load(resp)
    df = pd.DataFrame(raw, columns=[
        "date", "open", "high", "low", "close", "volume",
        "close_time", "quote_volume", "trades", "taker_buy_base",
        "taker_buy_quote", "ignore",
    ])
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = df[col].astype(float)
    df["date"] = pd.to_datetime(df["date"], unit="ms", utc=True)
    return df


def _populate_indicators(dataframe: pd.DataFrame) -> pd.DataFrame:
    dataframe = dataframe.copy()
    macd = ta.MACD(dataframe)
    dataframe["macd"] = macd["macd"]
    dataframe["macdsignal"] = macd["macdsignal"]
    dataframe["macdhist"] = macd["macdhist"]
    dataframe["rsi"] = ta.RSI(dataframe)
    bollinger = qtpylib.bollinger_bands(qtpylib.typical_price(dataframe), window=20, stds=2)
    dataframe["bb_middleband"] = bollinger["mid"]
    dataframe["tema"] = ta.TEMA(dataframe, timeperiod=9)
    return dataframe


def predict_pm_direction(symbol: str) -> FreqtradePmSignal | None:
    """SampleStrategy entry kuralları + momentum oylaması → UP/DOWN."""
    try:
        df = _populate_indicators(_fetch_klines(symbol))
    except Exception as exc:
        print(f"[analiz3_signal] {symbol} veri hatasi: {exc}")
        return None

    if len(df) < 30:
        return None

    last = df.iloc[-1]
    prev = df.iloc[-2]
    price = float(last["close"])
    rsi = float(last["rsi"]) if pd.notna(last["rsi"]) else 50.0
    macd_bull = float(last["macdhist"]) > 0 if pd.notna(last["macdhist"]) else False
    tema = float(last["tema"]) if pd.notna(last["tema"]) else price
    tema_prev = float(prev["tema"]) if pd.notna(prev["tema"]) else tema
    tema_rising = tema > tema_prev
    bb_mid = float(last["bb_middleband"]) if pd.notna(last["bb_middleband"]) else price

    long_bias = bool(
        qtpylib.crossed_above(df["rsi"], BUY_RSI).iloc[-1]
        and tema <= bb_mid
        and tema_rising
        and float(last["volume"]) > 0
    )
    short_bias = bool(
        qtpylib.crossed_above(df["rsi"], SHORT_RSI).iloc[-1]
        and tema > bb_mid
        and not tema_rising
        and float(last["volume"]) > 0
    )

    score = 0
    if rsi >= 50:
        score += 1
    else:
        score -= 1
    if tema_rising:
        score += 1
    else:
        score -= 1
    if macd_bull:
        score += 1
    else:
        score -= 1
    if long_bias:
        score += 2
    if short_bias:
        score -= 2

    predicted = "UP" if score >= 0 else "DOWN"
    strength = min(abs(score) / 5.0, 1.0)
    prob_up = 0.5 + strength / 2 if predicted == "UP" else 0.5 - strength / 2
    prob_down = 1.0 - prob_up

    if tema_rising and price > tema:
        trend = "YUKARI"
    elif not tema_rising and price < tema:
        trend = "ASAGI"
    else:
        trend = "NOTR"

    return FreqtradePmSignal(
        symbol=symbol,
        predicted_dir=predicted,
        current_price=price,
        rsi=rsi,
        macd_bull=macd_bull,
        tema_rising=tema_rising,
        long_bias=long_bias,
        short_bias=short_bias,
        prob_up=prob_up,
        prob_down=prob_down,
        trend=trend,
    )
