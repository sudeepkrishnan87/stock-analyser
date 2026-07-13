from pydantic import BaseModel
from typing import Optional, List


class TokenRequest(BaseModel):
    access_token: str


class TokenStatus(BaseModel):
    authenticated: bool
    message: str


class CandleData(BaseModel):
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: int


class CandlestickPattern(BaseModel):
    date: str
    pattern: str
    signal: str  # bullish | bearish | neutral
    description: str


class ElliottWave(BaseModel):
    wave_number: str  # "1","2","3","4","5","A","B","C"
    start_date: str
    end_date: str
    start_price: float
    end_price: float
    wave_type: str  # motive | corrective


class FibonacciLevel(BaseModel):
    level: float
    price: float
    label: str


class TechnicalIndicators(BaseModel):
    rsi: Optional[float] = None
    macd: Optional[float] = None
    macd_signal: Optional[float] = None
    macd_histogram: Optional[float] = None
    bb_upper: Optional[float] = None
    bb_middle: Optional[float] = None
    bb_lower: Optional[float] = None
    sma_20: Optional[float] = None
    sma_50: Optional[float] = None
    sma_200: Optional[float] = None
    volume_ratio: Optional[float] = None  # current vol / 20-day avg vol


class FiiDiiEntry(BaseModel):
    date: str
    fii_buy: float
    fii_sell: float
    fii_net: float
    dii_buy: float
    dii_sell: float
    dii_net: float


class QuarterlyResult(BaseModel):
    quarter: str
    revenue: Optional[float] = None
    net_profit: Optional[float] = None
    eps: Optional[float] = None


class AIAnalysis(BaseModel):
    signal: str          # BUY | SELL | HOLD
    confidence: str      # HIGH | MEDIUM | LOW
    price_target: Optional[float] = None
    stop_loss: Optional[float] = None
    time_horizon: str
    elliott_wave_position: str
    pattern_summary: str
    fii_dii_sentiment: str
    quarterly_outlook: str
    narrative: str
    key_risks: List[str]


class StockAnalysisResponse(BaseModel):
    symbol: str
    company_name: str
    current_price: float
    daily_candles: List[CandleData]
    weekly_candles: List[CandleData]
    monthly_candles: List[CandleData]
    candlestick_patterns: List[CandlestickPattern]
    elliott_waves: List[ElliottWave]
    fibonacci_levels: List[FibonacciLevel]
    technical_indicators: TechnicalIndicators
    fii_dii_data: List[FiiDiiEntry]
    quarterly_results: List[QuarterlyResult]
    ai_analysis: AIAnalysis
