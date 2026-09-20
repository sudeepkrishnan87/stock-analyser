# Jarvis — Trading Enrichment Roadmap (30-year-trader lens)

> **Status: analysis only, nothing here is implemented yet.** This is meant to be read and understood — even practiced manually (checking these gaps yourself in the live app/logs) — before any of it gets built. When you're ready for one of these, say which item number and it'll get scoped into an actual implementation plan.

## Context

Written from a "30-year trader" review of the app — no code changes, just an honest audit of where the system is strong and where it's not, and how to play smartly from here. Every claim below was verified directly against the current codebase (not from memory/docs) via a full pass over `screener_service.py`, `trading_service.py`, `scheduler_service.py`, `config.py`, and the four analytical services (`elliott_wave_service.py`, `trendline_service.py`, `candlestick_service.py`, `fundamental_service.py`), plus two facts hand-verified directly: the daily-loss gate's realized-only scope, and the scheduler's actual 09:00–15:45 window vs. the docstring's claimed 09:30–15:15.

**The headline verdict**: this system's *trade-level* risk management is already solid — 2% risk/trade, R:R ≥ 1.5 gate, real-funds-capped sizing, trailing stop, 50%-partial-profit-taking with breakeven runner protection, correct per-symbol tick sizing, CDSL/DDPI-aware exit alerting. What's missing is almost entirely at the **portfolio and market-context level** — the system has no concept of "is this a good day to trade," "am I accidentally making one big bet instead of five small ones," or "which of my 9 scoring factors are actually working." Those are the gaps a 30-year trader would flag first, not a 10th technical indicator.

---

## Tier 1 — Portfolio-level risk controls (highest priority: how not to blow up)

### 1. Sector/correlation concentration cap
**Finding**: `DEFAULT_WATCHLIST` (`config.py`) has 6 of 30 symbols in financials (`HDFCBANK, ICICIBANK, KOTAKBANK, SBIN, AXISBANK, BAJFINANCE`). `MAX_OPEN_POSITIONS=5` caps position *count*, not sector exposure — it's entirely possible for all 5 slots to fill with financial-sector names during a sector-wide move, which looks like "5 diversified positions" but is actually one leveraged bet on bank-sector beta.
**The data already exists**: `fundamental_service.fetch_fundamentals()` already fetches and returns `sector`/`industry` per symbol — it's fetched, put in the API response, and then never read again. This is a cheap fix precisely because the hard part (data) is already done.
**Fix**: in `can_enter_trade()` (`trading_service.py`), add a gate that counts open positions by sector and rejects a new entry if it would push any single sector above, e.g., 40% of open positions or 2 of 5 slots.
**Practice yourself**: next time you have 2+ open positions, check their sectors via `/api/scanner/symbol/{symbol}` (look at `fundamentals.sector`) before approving a 3rd — would it concentrate you?

### 2. Daily-loss circuit breaker is blind to unrealized drawdown
**Finding** (hand-verified, `trading_service.py:173-178`): `daily_pnl` sums only `closed_trades` where `exit_time` starts with today. The `DAILY_LOSS_LIMIT_PCT` (3%) gate in `can_enter_trade()` checks this realized-only figure. If you're deep underwater on open positions that haven't hit their individual stop-losses yet, the system will happily keep opening *new* positions on a day that's already going badly — the circuit breaker doesn't trip until losses are locked in.
**Fix**: extend the daily-loss check to include unrealized P&L on open positions (`sum(pos.current_pnl(live_ltp) for pos in positions)`), not just realized. This is the single highest-leverage "prevent a bad day from becoming a terrible day" fix in the whole system.
**Practice yourself**: on a red day, manually check `GET /api/trading/portfolio` and eyeball unrealized P&L on open positions before approving anything new — you're currently the circuit breaker for this specific gap.

### 3. No market-regime / index-trend filter
**Finding**: zero references to Nifty/Sensex/any benchmark index anywhere in the scan/entry pipeline. The system takes individual-stock LONG signals with total indifference to whether the broader market is trending up, down, or chopping — a classic way to get chewed up taking "textbook" long setups into a falling market.
**Fix**: fetch Nifty 50 daily trend (already have `broker.fetch_historical` — same mechanism used per-symbol) once per scan cycle, compute a simple trend read (e.g., price vs. SMA50/SMA200), and require it to not be *actively working against* the signal's direction before queuing (or at minimum, surface it as a warning in the signal card so you see it before approving).
**Practice yourself**: before approving any LONG signal, glance at the Nifty 50 chart yourself — is it trending the same way as the individual stock you're about to buy?

### 4. No volatility-regime awareness (India VIX)
**Finding**: zero VIX references anywhere. Fixed 2% risk and fixed 3%/8% stop/target percentages are applied identically whether the market is calm or in a VIX spike — exactly when a fixed-percentage stop is most likely to get blown through by noise, not a real move.
**Fix**: pull India VIX (available via NSE or Kite's index quote), and when it's elevated (e.g., >20), either tighten the entry score bar (require STRONG not just BUY/SELL) or reduce position size proportionally. Lower priority than #1-3 since it requires a new data source, but cheap once wired.
**Practice yourself**: check India VIX yourself before a trading day (NSE website or any broker terminal) — above ~20, be more selective about which signals you actually approve.

### 5. No liquidity/ADV floor before entry
**Finding**: `volume_ratio` (today's volume ÷ 20-day average) is used only as a *relative* scoring signal, never as an absolute liquidity screen. A stock with genuinely thin average volume can still score well on relative volume spike and get sized with real capital, risking slippage on both entry and (worse) exit.
**Fix**: add a minimum average-daily-volume/value floor (e.g., ₹5-10 Cr average daily turnover) as a pre-scan filter — cheap, and directly protects execution quality, which matters more as capital grows.

---

## Tier 2 — Signal quality (win more of the trades you do take)

### 6. No trend-strength (ADX) filter → choppy-market whipsaws
**Finding**: `technical_service.compute_indicators()` computes RSI/MACD/Bollinger/SMA/volume_ratio only — no ADX or equivalent. MACD-crossover and RSI-zone scoring (worth 25 of the 130 points) are precisely the factors most prone to false signals in a range-bound, non-trending market.
**Fix**: add ADX(14) as a 10th factor, or better, as a *gate* (require ADX > ~20-25 before honoring MACD/SMA-trend scores at full weight) rather than just another additive score — this is about filtering out bad regimes, not finding more reasons to buy.
**Practice yourself**: pull up a chart of any signal before approving — does it look like it's genuinely trending, or bouncing sideways in a range? ADX is the mechanical version of that eyeball check.

### 7. No multi-timeframe confirmation
**Finding**: `scan_intraday()` (15-min candles) and the daily scans run in complete isolation — nothing checks "does the daily chart agree with this 15-min signal" before acting. This is one of the most reliable classic edges (trade with the higher-timeframe trend, not against it) and it's currently unused.
**Fix**: for intraday signals specifically, add a cheap daily-trend check (reuse the daily data already fetched by the premarket scan that same morning) and either boost score or require agreement before an intraday STRONG BUY/SELL alerts.
**Practice yourself**: when an intraday signal comes in, check the Research tab's daily chart for that symbol before approving — does the daily trend agree with the 15-min signal, or are you fighting the bigger picture?

### 8. Intraday scanning has no time-of-day awareness
**Finding** (from a real incident investigated this session): every 15-min tick from 09:00 to 15:45 runs identical scoring with an identical volume-confirmation bar (≥1.5x average). Around midday (12:00-13:30 IST), NSE volume genuinely thins to 20-90% of average — measured this live across 10 symbols. The compound "STRONG signal + live volume-confirmed breakout" gate is structurally much harder to clear midday, which is exactly why *zero* SHORT alerts and *zero* INTRADAY-sourced LONG alerts fired in 2+ full weeks (only Premarket/Swing signals fired, which don't require the breakout gate).
**Fix**: either (a) relax the volume-confirmation threshold or widen the lookback window during 12:00-13:30, or (b) accept STRONG BUY/SELL alone (raise the score bar to ~80 instead) as an alternate alert path that doesn't require the same-candle breakout confirmation. This directly fixes the "not getting alerts" symptom, not just explains it.
**Practice yourself**: if you're manually researching stocks in the Research tab, know that midday checks are less likely to show a live breakout/breakdown regardless of how good the underlying setup looks — the open (9:15-10:30) and close (2:30-3:15) windows are where volume-confirmed moves actually happen.

### 9. Fibonacci levels computed but never used for stop/target placement
**Finding**: `elliott_wave_service.detect_elliott_waves()` computes a full set of Fibonacci retracement/extension levels (`fib_levels`) — exposed via the API, feeds only the AI narrative. The actual `trade_suggestion`/`short_trade_suggestion` SL/target math in `screener_service.scan_symbol()` uses only flat 3%/8% defaults plus horizontal support/resistance clusters — never the Fib levels already sitting right there.
**Fix**: when a nearby Fib level (38.2%/50%/61.8%) sits between the flat-percentage default and current price, prefer it for SL/target placement — this is standard technical practice and the data is already computed, just unused.
**Practice yourself**: the Research tab's chart already shows Fibonacci levels — before approving a trade, check whether the app's flat-percentage SL/target actually makes sense against the nearest Fib level, or whether you'd manually place it differently.

### 10. `beta` fetched but unused for position sizing
**Finding**: `fundamental_service.fetch_fundamentals()` returns `beta` — computed, returned, never read. Position sizing (`calculate_position_size`) applies the same flat 2%-risk formula to a low-beta utility (NTPC) and a high-beta financial (BAJFINANCE) alike, even though the high-beta name will hit a given %-stop faster and with more noise.
**Fix**: scale position size down slightly for beta > ~1.3, up slightly for beta < ~0.7 — small, mechanical, uses data you're already paying the API call for.

---

## Tier 3 — The compounding loop ("billionaire journey" framing)

### 11. No factor-level or source-level performance analytics
**Finding**: `Position`/`ClosedTrade` already persist `signal_score`, `source`, and `reason` specifically so trades "stay analyzable" (per the code's own comments) — but nothing in the codebase actually aggregates win-rate by score band, by source (Premarket/Intraday/Swing), by individual scoring factor, or by symbol. `TradeState.win_rate()` computes one flat overall number.
**Why this is actually the most important item on this whole list**: every other recommendation here (ADX gate, VIX sizing, sector caps, Fib-based stops) is currently a plausible guess, including mine. You now have real trade history (KOTAKBANK, NTPC, WIPRO, and more as they close). Without breaking down which signals actually worked, every future tuning decision — including everything above — stays a guess dressed up as expertise. This is cheap to build (the data's already in `trades.json`) and it's the thing that turns "a system I built" into "a system I'm actually improving based on evidence."
**Fix**: add a `/api/trading/analytics` endpoint (or extend the Trade Book UI) that groups closed trades by `source`, by `signal_score` bucket (60-74/75-89/90+), and by direction (LONG/SHORT), showing win rate and average R multiple for each. Do this **before**, or at latest alongside, Tier 1/2 changes — it's how you'll know whether they actually helped.
**Practice yourself**: until this exists, manually skim the Trade Book tab periodically and ask yourself — are PREMARKET signals actually outperforming SWING signals? Are higher-score trades actually winning more? You're doing the analysis by eye that #11 would automate.

### 12. Capital compounding is still a manual step
**Finding**: the `_effective_capital()` fix (already shipped) self-corrects the *risk ceiling* upward as real broker funds grow, so you no longer get silently strangled — but `TRADING_CAPITAL`, and by extension the 2%-per-trade risk amount, isn't tied to the system's own proven edge. As the win-rate analytics above start showing a real, positive edge, risk-per-trade could scale with it (a soft form of the Kelly criterion) instead of staying flat at 2% forever regardless of how well it's actually performing.
**Fix**: once #11 exists and shows a stable edge over a meaningful sample (suggest 50+ closed trades before touching this), consider a modest, capped adjustment — e.g., 1.5-2.5% band instead of a hard 2% — tied to trailing 30-trade win rate. Deliberately last on this list: sizing changes are the highest-blast-radius category here, and should be the last thing tuned, not the first.

---

## Tier 4 — Coverage and opportunity expansion

### 13. No earnings-date/corporate-action awareness
**Finding**: `nse_service.fetch_quarterly_results()` exists but only feeds the manual Research-tab AI narrative — nothing in the scan/entry path checks whether a symbol has earnings due in the next few days before suggesting a SWING (multi-day hold) entry, which carries real gap risk into results.
**Fix**: a simple "don't queue a SWING signal within N days of known/estimated earnings" filter.
**Practice yourself**: before approving a SWING trade, check whether the company has earnings coming up in the next few days — the Research tab's Quarterly Results section shows past quarters, so you can estimate the next one's timing.

### 14. Fixed 30-symbol large-cap-only watchlist
**Finding**: `DEFAULT_WATCHLIST` is a hardcoded, static list of large-caps. Momentum/breakout opportunities in mid-caps or in symbols outside this list are structurally invisible to the scanner, no matter how strong the setup.
**Fix**: lowest priority — either a periodic (e.g., weekly) refresh against an NSE most-active/top-gainers screen, or just manually rotating the list occasionally. Not urgent; the current list already gives reasonable liquidity and coverage for the capital sizes discussed this session.

---

## What I'd explicitly avoid

Adding an 11th, 12th, 13th technical indicator to the composite score. The system already scores volume, RSI, Bollinger, candlesticks, MACD, SMA trend, Elliott wave, and trendline breakout/breakdown — 9 factors, mirrored for both directions. "Indicator collecting" is the classic amateur mistake this system has already avoided; the gaps above are about *context* (market regime, portfolio concentration, liquidity, evidence) not about finding more reasons to enter a trade.

## Suggested order, when you're ready to build

1. **#11 analytics first** — you need the measurement tool before you tune anything else, or you're just guessing with extra steps.
2. **#2 (unrealized-drawdown daily-loss gate) + #1 (sector cap)** — both are small, self-contained, high-value, and directly prevent a bad day/bad sector-correlated bet from compounding.
3. **#8 (time-of-day alert gate fix)** — directly resolves the "no short alerts" symptom.
4. **#6 (ADX filter) + #7 (multi-timeframe confirmation)** — meaningfully improves win rate on signals that do fire.
5. Everything else in Tier 1/2 (#3, #4, #5, #9, #10), then Tier 3/4, roughly in the order listed — each is progressively more work or more dependent on the analytics from #11 actually existing first.
