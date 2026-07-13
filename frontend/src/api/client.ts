import axios, { type InternalAxiosRequestConfig } from "axios";
import type { StockAnalysisResponse } from "../types";

// ── API key must match API_SECRET_KEY in backend .env ─────────────────────
// Store in localStorage so you only paste it once
const getApiKey = () => localStorage.getItem("jarvis_api_key") || "";
export const setApiKey = (key: string) => localStorage.setItem("jarvis_api_key", key);
export const hasApiKey = () => !!getApiKey();

const api = axios.create({
  baseURL: "/api",
  timeout: 120_000,
});

// Attach API key to every request automatically
api.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const key = getApiKey();
  if (key) config.headers["X-API-Key"] = key;
  return config;
});

// ── Auth ──────────────────────────────────────────────────────────────────
export async function checkAuthStatus() {
  const { data } = await api.get("/auth/status");
  return data as { authenticated: boolean; message: string };
}

export async function getLoginUrl(): Promise<string> {
  const { data } = await api.get("/auth/login-url");
  return data.login_url;
}

// Fallback: manually paste a Kite access token
export async function setKiteToken(token: string): Promise<{ authenticated: boolean; message: string }> {
  const { data } = await api.post("/auth/token", { access_token: token });
  return data;
}

export async function clearKiteToken(): Promise<void> {
  await api.delete("/auth/token");
}

// ── Stock analysis ────────────────────────────────────────────────────────
export async function analyzeStock(symbol: string): Promise<StockAnalysisResponse> {
  const { data } = await api.get(`/stock/${encodeURIComponent(symbol)}`);
  return data;
}

export async function searchSymbols(query: string): Promise<{ symbol: string; name: string }[]> {
  const { data } = await api.get(`/stock/search/${encodeURIComponent(query)}`);
  return data.results;
}

// ── Scanner ───────────────────────────────────────────────────────────────
export async function scanWatchlist(minScore = 55) {
  const { data } = await api.get(`/scanner/watchlist?min_score=${minScore}`);
  return data;
}

export async function scanIntraday() {
  const { data } = await api.get("/scanner/intraday");
  return data;
}

export async function scanSymbol(symbol: string) {
  const { data } = await api.get(`/scanner/symbol/${symbol}?include_fundamentals=true`);
  return data;
}

export async function triggerScan(type: "swing" | "intraday" | "premarket") {
  const { data } = await api.post(`/scanner/trigger/${type}`);
  return data;
}

// ── Trading ───────────────────────────────────────────────────────────────
export async function getPortfolio() {
  const { data } = await api.get("/trading/portfolio");
  return data;
}

export async function getOpenPositions() {
  const { data } = await api.get("/trading/positions");
  return data;
}

export async function getTradeHistory() {
  const { data } = await api.get("/trading/history");
  return data;
}

export async function dryRunTrade(payload: {
  symbol: string; direction: string; entry_price: number;
  stop_loss: number; target: number; trade_type: string;
}) {
  const { data } = await api.post("/trading/dry-run", payload);
  return data;
}

export async function enterTrade(payload: {
  symbol: string; direction: string; entry_price: number;
  stop_loss: number; target: number; trade_type: string; product: string;
}) {
  const { data } = await api.post("/trading/enter", payload);
  return data;
}

export async function exitTrade(symbol: string) {
  const { data } = await api.post(`/trading/exit/${symbol}`);
  return data;
}

export async function monitorPositions() {
  const { data } = await api.post("/trading/monitor");
  return data;
}

// ── Alerts ────────────────────────────────────────────────────────────────
export async function getAlertHistory() {
  const { data } = await api.get("/alerts/history");
  return data;
}

export async function testEmail() {
  const { data } = await api.post("/alerts/test/email");
  return data;
}

export async function testWhatsApp() {
  const { data } = await api.post("/alerts/test/whatsapp");
  return data;
}

// ── FII/DII ───────────────────────────────────────────────────────────────
export async function getFiiDii(days = 30) {
  const { data } = await api.get(`/fii-dii/?days=${days}`);
  return data;
}

// ── Health ────────────────────────────────────────────────────────────────
export async function getHealth() {
  // Health is public — no API key needed
  const { data } = await axios.get("/api/health");
  return data;
}
