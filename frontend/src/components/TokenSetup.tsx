import { useState } from "react";
import { setKiteToken, getLoginUrl, triggerAutoLogin } from "../api/client";

interface Props {
  onSuccess: () => void;
  onClose: () => void;
}

export default function TokenSetup({ onSuccess, onClose }: Props) {
  const [token, setToken] = useState("");
  const [loading, setLoading] = useState(false);
  const [autoLoading, setAutoLoading] = useState(false);
  const [error, setError] = useState("");
  const [loginUrl, setLoginUrl] = useState("");
  const [showManual, setShowManual] = useState(false);

  const handleAutoLogin = async () => {
    setAutoLoading(true);
    setError("");
    try {
      const result = await triggerAutoLogin();
      if (result.success) {
        onSuccess();
      }
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        "Auto-login failed. Check that ZERODHA_USER_ID, ZERODHA_PASSWORD and ZERODHA_TOTP_SECRET are set in server config.";
      setError(msg);
      setShowManual(true);
    } finally {
      setAutoLoading(false);
    }
  };

  const handleGetLoginUrl = async () => {
    try {
      const url = await getLoginUrl();
      setLoginUrl(url);
      window.open(url, "_blank");
    } catch {
      setError("Could not fetch login URL. Ensure KITE_API_KEY is configured on the server.");
    }
  };

  const handleSubmit = async () => {
    if (!token.trim()) return;
    setLoading(true);
    setError("");
    try {
      const result = await setKiteToken(token.trim());
      if (result.authenticated) {
        onSuccess();
      }
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        "Invalid token. Please try again.";
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/70 z-50 flex items-center justify-center p-4">
      <div className="bg-slate-800 border border-slate-700 rounded-2xl w-full max-w-md p-6 shadow-2xl">
        <div className="flex items-center justify-between mb-5">
          <h2 className="text-lg font-semibold">Zerodha Kite Setup</h2>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-200 text-xl">✕</button>
        </div>

        <div className="space-y-4 text-sm text-slate-300">

          {/* Primary: Auto-login */}
          <div className="bg-slate-900/60 rounded-lg p-4 space-y-2 text-xs text-slate-400">
            <p className="font-medium text-slate-300">Option 1 — Auto-login (recommended)</p>
            <p>Uses your configured TOTP credentials to authenticate automatically. No browser login needed.</p>
          </div>

          <button
            onClick={handleAutoLogin}
            disabled={autoLoading}
            className="w-full bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed py-2.5 rounded-lg font-medium transition-colors"
          >
            {autoLoading ? "Authenticating via TOTP…" : "Auto-Login with TOTP"}
          </button>

          {/* Divider */}
          <div className="flex items-center gap-3 text-xs text-slate-600">
            <div className="flex-1 h-px bg-slate-700" />
            <span>or do it manually</span>
            <div className="flex-1 h-px bg-slate-700" />
          </div>

          {/* Secondary: OAuth callback */}
          <div className="bg-slate-900/60 rounded-lg p-3 text-xs text-slate-400">
            <p className="font-medium text-slate-300 mb-1">Option 2 — Browser login</p>
            <ol className="list-decimal list-inside space-y-1">
              <li>Click "Open Kite Login" → log in on Zerodha</li>
              <li>Zerodha redirects back → token set automatically</li>
              <li>If redirect fails, copy <code className="bg-slate-700 px-1 rounded">request_token</code> from URL bar and call <code className="bg-slate-700 px-1 rounded">/api/auth/exchange?request_token=…</code></li>
            </ol>
          </div>

          <button
            onClick={handleGetLoginUrl}
            className="w-full bg-slate-700 hover:bg-slate-600 py-2.5 rounded-lg transition-colors text-sm"
          >
            Open Kite Login →
          </button>

          {loginUrl && (
            <div className="bg-slate-900 rounded p-2 break-all text-xs text-slate-500 select-all">
              {loginUrl}
            </div>
          )}

          {/* Tertiary: paste token */}
          <button
            onClick={() => setShowManual(!showManual)}
            className="w-full text-xs text-slate-500 hover:text-slate-400 transition-colors py-1"
          >
            {showManual ? "Hide manual paste" : "Paste access token manually →"}
          </button>

          {showManual && (
            <div className="space-y-2">
              <label className="block text-xs text-slate-400">Paste Access Token</label>
              <textarea
                value={token}
                onChange={(e) => setToken(e.target.value)}
                placeholder="Paste your Kite access token here…"
                rows={3}
                className="w-full bg-slate-900 border border-slate-600 rounded-lg px-3 py-2 text-xs focus:outline-none focus:border-indigo-500 resize-none font-mono"
              />
              <button
                onClick={handleSubmit}
                disabled={loading || !token.trim()}
                className="w-full bg-slate-600 hover:bg-slate-500 disabled:opacity-50 disabled:cursor-not-allowed py-2 rounded-lg text-sm transition-colors"
              >
                {loading ? "Verifying…" : "Connect with pasted token"}
              </button>
            </div>
          )}

          {error && (
            <p className="text-red-400 text-xs bg-red-900/20 border border-red-700/40 rounded p-2">{error}</p>
          )}
        </div>
      </div>
    </div>
  );
}
