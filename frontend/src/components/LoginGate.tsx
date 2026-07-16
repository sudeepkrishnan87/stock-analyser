import { useState, useRef, useEffect } from "react";
import { setApiKey } from "../api/client";

interface Props {
  onLogin: (zerodhaAuthenticated: boolean) => void;
}

export default function LoginGate({ onLogin }: Props) {
  const [key, setKey] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!key.trim()) return;
    setLoading(true);
    setError("");

    setApiKey(key.trim());

    try {
      // Importing here so the key is already in localStorage when the request fires
      const { checkAuthStatus } = await import("../api/client");
      const status = await checkAuthStatus();
      onLogin(status.authenticated);
    } catch {
      // 401 = wrong key. Clear it so requests don't keep failing.
      localStorage.removeItem("jarvis_api_key");
      setError("Invalid access key. Try again.");
      setKey("");
      inputRef.current?.focus();
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 flex items-center justify-center px-4">
      <div className="w-full max-w-sm space-y-8">

        {/* Logo */}
        <div className="text-center space-y-2">
          <div className="w-14 h-14 bg-indigo-600 rounded-2xl flex items-center justify-center font-bold text-2xl mx-auto shadow-lg shadow-indigo-600/30">
            J
          </div>
          <h1 className="text-2xl font-bold text-slate-100 tracking-tight">Jarvis</h1>
          <p className="text-slate-500 text-sm">AI Stock Analyst · Indian Markets</p>
        </div>

        {/* Login form */}
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs text-slate-400 mb-1.5 font-medium">
              Access Key
            </label>
            <input
              ref={inputRef}
              type="password"
              value={key}
              onChange={(e) => { setKey(e.target.value); setError(""); }}
              placeholder="Enter your access key"
              className="w-full bg-slate-800 border border-slate-700 focus:border-indigo-500 rounded-xl px-4 py-3 text-slate-100 placeholder-slate-600 outline-none transition-colors font-mono text-sm"
              autoComplete="current-password"
            />
          </div>

          {error && (
            <p className="text-red-400 text-xs bg-red-900/20 border border-red-700/30 rounded-lg px-3 py-2">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={loading || !key.trim()}
            className="w-full bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 disabled:cursor-not-allowed py-3 rounded-xl font-semibold text-sm transition-colors shadow-lg shadow-indigo-600/20"
          >
            {loading ? "Verifying…" : "Enter"}
          </button>
        </form>

        <p className="text-center text-slate-700 text-xs">
          Personal access only · Single-user
        </p>
      </div>
    </div>
  );
}
