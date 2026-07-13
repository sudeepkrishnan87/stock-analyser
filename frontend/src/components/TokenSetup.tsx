import { useState } from "react";
import { setKiteToken, getLoginUrl } from "../api/client";

interface Props {
  onSuccess: () => void;
  onClose: () => void;
}

export default function TokenSetup({ onSuccess, onClose }: Props) {
  const [token, setToken] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [loginUrl, setLoginUrl] = useState("");

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
          <div className="bg-slate-900/60 rounded-lg p-4 space-y-2 text-xs text-slate-400">
            <p className="font-medium text-slate-300">How to get your access token:</p>
            <ol className="list-decimal list-inside space-y-1">
              <li>Click "Open Kite Login" below</li>
              <li>Log in with your Zerodha credentials</li>
              <li>After login, you'll be redirected — copy the <code className="bg-slate-700 px-1 rounded">access_token</code> from the URL or your Kite Connect dashboard</li>
              <li>Paste it below</li>
            </ol>
            <p className="text-amber-400 mt-2">Note: Kite access tokens expire daily. You'll need to do this once per day.</p>
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

          <div>
            <label className="block text-xs text-slate-400 mb-1">Paste Access Token</label>
            <textarea
              value={token}
              onChange={(e) => setToken(e.target.value)}
              placeholder="Paste your Kite access token here…"
              rows={3}
              className="w-full bg-slate-900 border border-slate-600 rounded-lg px-3 py-2 text-xs focus:outline-none focus:border-indigo-500 resize-none font-mono"
            />
          </div>

          {error && (
            <p className="text-red-400 text-xs bg-red-900/20 border border-red-700/40 rounded p-2">{error}</p>
          )}

          <button
            onClick={handleSubmit}
            disabled={loading || !token.trim()}
            className="w-full bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed py-2.5 rounded-lg font-medium transition-colors"
          >
            {loading ? "Verifying…" : "Connect"}
          </button>
        </div>
      </div>
    </div>
  );
}
