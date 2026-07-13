export interface CandleData {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface CandlestickPattern {
  date: string;
  pattern: string;
  signal: "bullish" | "bearish" | "neutral";
  description: string;
}

export interface ElliottWave {
  wave_number: string;
  start_date: string;
  end_date: string;
  start_price: number;
  end_price: number;
  wave_type: "motive" | "corrective";
}

export interface FibonacciLevel {
  level: number;
  price: number;
  label: string;
}

export interface TechnicalIndicators {
  rsi?: number;
  macd?: number;
  macd_signal?: number;
  macd_histogram?: number;
  bb_upper?: number;
  bb_middle?: number;
  bb_lower?: number;
  sma_20?: number;
  sma_50?: number;
  sma_200?: number;
  volume_ratio?: number;
}

export interface FiiDiiEntry {
  date: string;
  fii_buy: number;
  fii_sell: number;
  fii_net: number;
  dii_buy: number;
  dii_sell: number;
  dii_net: number;
}

export interface QuarterlyResult {
  quarter: string;
  revenue?: number;
  net_profit?: number;
  eps?: number;
}

export interface AIAnalysis {
  signal: "BUY" | "SELL" | "HOLD";
  confidence: "HIGH" | "MEDIUM" | "LOW";
  price_target?: number;
  stop_loss?: number;
  time_horizon: string;
  elliott_wave_position: string;
  pattern_summary: string;
  fii_dii_sentiment: string;
  quarterly_outlook: string;
  narrative: string;
  key_risks: string[];
}

export interface StockAnalysisResponse {
  symbol: string;
  company_name: string;
  current_price: number;
  daily_candles: CandleData[];
  weekly_candles: CandleData[];
  monthly_candles: CandleData[];
  candlestick_patterns: CandlestickPattern[];
  elliott_waves: ElliottWave[];
  fibonacci_levels: FibonacciLevel[];
  technical_indicators: TechnicalIndicators;
  fii_dii_data: FiiDiiEntry[];
  quarterly_results: QuarterlyResult[];
  ai_analysis: AIAnalysis;
}
