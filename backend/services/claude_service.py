import json
import anthropic
from typing import List, Dict, Optional
from config import settings

FALLBACK_ANALYSIS = {
    "signal": "HOLD",
    "confidence": "LOW",
    "price_target": None,
    "stop_loss": None,
    "time_horizon": "N/A",
    "elliott_wave_position": "Unable to determine — insufficient data",
    "pattern_summary": "Analysis unavailable",
    "fii_dii_sentiment": "Analysis unavailable",
    "quarterly_outlook": "Analysis unavailable",
    "narrative": "AI analysis could not be completed. Please check your Anthropic API key.",
    "key_risks": ["API key not configured", "Insufficient data"],
}


def _format_patterns(patterns: List[Dict]) -> str:
    if not patterns:
        return "No significant patterns detected in recent candles."
    lines = [f"- {p['date']}: {p['pattern']} ({p['signal'].upper()}) — {p['description']}"
             for p in patterns[:8]]
    return "\n".join(lines)


def _format_waves(waves: List[Dict]) -> str:
    if not waves:
        return "Wave structure unclear — insufficient pivot data."
    lines = [
        f"- Wave {w['wave_number']} ({w['wave_type']}): {w['start_date']} @ ₹{w['start_price']:,.2f} → {w['end_date']} @ ₹{w['end_price']:,.2f}"
        for w in waves
    ]
    return "\n".join(lines)


def _format_fibonacci(levels: List[Dict]) -> str:
    if not levels:
        return "No Fibonacci levels calculated."
    lines = [f"- {l['label']}: ₹{l['price']:,.2f}" for l in levels[:8]]
    return "\n".join(lines)


def _format_fii_dii(data: List[Dict]) -> str:
    if not data:
        return "FII/DII data not available."
    recent = data[-10:]
    lines = [
        f"- {d['date']}: FII Net ₹{d['fii_net']:,.0f}Cr | DII Net ₹{d['dii_net']:,.0f}Cr"
        for d in recent
    ]
    return "\n".join(lines)


def _format_quarterly(results: List[Dict]) -> str:
    if not results:
        return "Quarterly results not available."
    lines = []
    for q in results:
        rev = f"₹{q['revenue']:,.0f}Cr" if q.get("revenue") else "N/A"
        np_ = f"₹{q['net_profit']:,.0f}Cr" if q.get("net_profit") else "N/A"
        lines.append(f"- {q['quarter']}: Revenue {rev} | Net Profit {np_}")
    return "\n".join(lines)


def generate_ai_analysis(
    symbol: str,
    current_price: float,
    technical_indicators: dict,
    candlestick_patterns: List[Dict],
    elliott_waves: List[Dict],
    fibonacci_levels: List[Dict],
    fii_dii_data: List[Dict],
    quarterly_results: List[Dict],
) -> dict:
    """
    Call Claude API to generate comprehensive stock analysis.
    Uses streaming with get_final_message() to handle large outputs.
    """
    if not settings.ANTHROPIC_API_KEY:
        return FALLBACK_ANALYSIS

    ind = technical_indicators
    prompt = f"""You are an expert technical analyst specializing in Elliott Wave theory, price action, and Indian equity markets (NSE/BSE). Analyze the following data for {symbol} and provide a comprehensive trading recommendation.

## Stock: {symbol}
## Current Market Price: ₹{current_price:,.2f}

## Technical Indicators (Latest):
- RSI (14): {ind.get('rsi', 'N/A')}
- MACD: {ind.get('macd', 'N/A')} | Signal: {ind.get('macd_signal', 'N/A')} | Histogram: {ind.get('macd_histogram', 'N/A')}
- Bollinger Bands: Upper ₹{ind.get('bb_upper', 'N/A')} | Mid ₹{ind.get('bb_middle', 'N/A')} | Lower ₹{ind.get('bb_lower', 'N/A')}
- SMA 20: ₹{ind.get('sma_20', 'N/A')} | SMA 50: ₹{ind.get('sma_50', 'N/A')} | SMA 200: ₹{ind.get('sma_200', 'N/A')}
- Volume Ratio (vs 20-day avg): {ind.get('volume_ratio', 'N/A')}x

## Recent Candlestick Patterns (last 30 trading days):
{_format_patterns(candlestick_patterns)}

## Elliott Wave Structure (Auto-detected):
{_format_waves(elliott_waves)}

## Fibonacci Levels (based on last significant swing):
{_format_fibonacci(fibonacci_levels)}

## FII/DII Net Activity (₹ Crores, last 10 sessions):
{_format_fii_dii(fii_dii_data)}

## Quarterly Financial Results:
{_format_quarterly(quarterly_results)}

Based on this comprehensive analysis, provide your trading recommendation. Return ONLY valid JSON (no markdown, no preamble) with this exact structure:

{{
  "signal": "BUY" or "SELL" or "HOLD",
  "confidence": "HIGH" or "MEDIUM" or "LOW",
  "price_target": <realistic number in INR within time horizon, or null>,
  "stop_loss": <key support/resistance for stop loss in INR, or null>,
  "time_horizon": "<e.g., 2-4 weeks, 1-3 months, 3-6 months>",
  "elliott_wave_position": "<which wave the stock is currently in and next expected move in 2-3 sentences>",
  "pattern_summary": "<2-3 sentences summarizing candlestick patterns and their implications>",
  "fii_dii_sentiment": "<2-3 sentences on institutional activity and what it signals>",
  "quarterly_outlook": "<2-3 sentences on fundamental trajectory based on quarterly data>",
  "narrative": "<5-7 sentences comprehensive analysis covering price action, trend, wave structure, and overall setup>",
  "key_risks": ["<risk1>", "<risk2>", "<risk3>"]
}}"""

    try:
        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

        with client.messages.stream(
            model="claude-opus-4-6",
            max_tokens=2000,
            thinking={"type": "adaptive"},
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            final_message = stream.get_final_message()

        # Extract text block (skip thinking blocks)
        response_text = ""
        for block in final_message.content:
            if block.type == "text":
                response_text = block.text.strip()
                break

        # Clean any accidental markdown fences
        if "```json" in response_text:
            start = response_text.find("```json") + 7
            end = response_text.find("```", start)
            response_text = response_text[start:end].strip()
        elif "```" in response_text:
            start = response_text.find("```") + 3
            end = response_text.find("```", start)
            response_text = response_text[start:end].strip()

        parsed = json.loads(response_text)
        # Ensure required keys exist
        for key in FALLBACK_ANALYSIS:
            if key not in parsed:
                parsed[key] = FALLBACK_ANALYSIS[key]
        return parsed

    except Exception as e:
        fallback = dict(FALLBACK_ANALYSIS)
        fallback["narrative"] = f"AI analysis error: {str(e)[:200]}"
        return fallback
