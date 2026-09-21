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

export interface PendingSignal {
  id: string;
  symbol: string;
  signal: string;
  signal_score: number;
  entry: number;
  stop_loss: number;
  target: number;
  rr_ratio: number;
  trade_type: string;
  source: "PREMARKET" | "INTRADAY" | "SWING";
  breakout_signal?: string | null;
  created_at: string;
  expires_at: string;
  status: "PENDING" | "APPROVED" | "REJECTED" | "EXPIRED";
  est_quantity: number;
  est_investment: number;
  est_available_funds: number;
  est_is_hypothetical: boolean;
  direction: "LONG" | "SHORT";
  resolution?: SignalResolution | null;
}

// Mirrors trading_service._position_size_breakdown() exactly — every intermediate
// number behind a "Position size is 0" rejection, so the Signals tab can show the
// actual arithmetic instead of just the one-line reason.
export interface SizingBreakdown {
  entry_price: number;
  stop_loss: number;
  capital: number;
  effective_capital: number;
  deployed_capital: number;
  available_funds: number | null;
  max_exposure_pct: number;
  max_deployable: number;
  risk_per_trade_pct: number;
  risk_amount: number;
  shares_from_risk: number;
  shares_from_exposure: number;
  shares_from_funds: number | null;
  final_shares: number;
}

export interface SignalResolution {
  status: string;
  reason?: string;
  sizing_breakdown?: SizingBreakdown;
  quantity?: number;
  entry_price?: number;
  symbol?: string;
}

export interface TradeSuggestion {
  entry: number;
  stop_loss: number;
  target: number;
  rr_ratio: number;
  trade_type: "SWING" | "INTRADAY";
  risk_reward: string;
}

// Minimal shape of GET /api/scanner/symbol/{symbol} actually used by the
// Research tab's Trade Setup card — the endpoint returns much more
// (indicators, waves, patterns) that this view doesn't need.
export interface ScanSymbolResult {
  symbol: string;
  signal: "STRONG BUY" | "BUY" | "WATCH" | "NEUTRAL";
  signal_score: number;
  current_price?: number;
  trade_suggestion?: TradeSuggestion;
  error?: string;
}

export interface DryRunResult {
  status: string;
  quantity: number;
  entry_price: number;
  limit_price: number;
  stop_loss: number;
  target: number;
  trade_type: string;
  risk_amount: number;
  max_profit: number;
  rr_ratio: number;
  reason?: string;
}

// Shared "why was this trade taken" fields — present on both open positions
// and closed trades, sourced from the signal that was approved (or "MANUAL"
// defaults for trades entered outside the Signals tab).
export interface TradeReasoning {
  signal_score: number;
  source: "PREMARKET" | "INTRADAY" | "SWING" | "MANUAL";
  reason: string;
  risk_amount: number;
  capital_at_entry: number;
}

export interface OpenPosition extends TradeReasoning {
  symbol: string;
  direction: "LONG" | "SHORT";
  quantity: number;
  entry_price: number;
  stop_loss: number;
  target: number;
  trade_type: "SWING" | "INTRADAY";
  entry_time: string;
  trailing_sl: number;
  trailing_activated: boolean;
  broker: string;
  order_id: string;
  partial_exit_done: boolean;
}

export interface ClosedTrade extends TradeReasoning {
  symbol: string;
  quantity: number;
  entry_price: number;
  exit_price: number;
  direction: "LONG" | "SHORT";
  trade_type: "SWING" | "INTRADAY";
  entry_time: string;
  exit_time: string;
  pnl: number;
  pnl_pct: number;
  exit_reason: string;
  order_id: string;
  broker: string;
}

export interface PortfolioSummary {
  capital: number;
  deployed_capital: number;
  deployment_pct: number;
  open_positions: number;
  positions: OpenPosition[];
  realized_pnl: number;
  daily_pnl: number;
  daily_pnl_pct: number;
  mtd_pnl: number;
  mtd_pnl_pct: number;
  qtd_pnl: number;
  qtd_pnl_pct: number;
  total_trades: number;
  win_rate: number;
  can_trade: boolean;
  trade_block_reason: string | null;
  timestamp: string;
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
