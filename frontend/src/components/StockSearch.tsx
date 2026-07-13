import { useState, type FormEvent } from "react";

interface Props {
  onSearch: (symbol: string) => void;
  loading: boolean;
}

const POPULAR = ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK", "WIPRO", "SBIN", "BAJFINANCE"];

export default function StockSearch({ onSearch, loading }: Props) {
  const [symbol, setSymbol] = useState("");

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    const s = symbol.trim().toUpperCase();
    if (s) onSearch(s);
  };

  return (
    <div className="bg-slate-800 rounded-xl p-6 border border-slate-700">
      <h2 className="text-sm font-medium text-slate-400 mb-3">Enter NSE Symbol</h2>
      <form onSubmit={handleSubmit} className="flex gap-3">
        <input
          type="text"
          value={symbol}
          onChange={(e) => setSymbol(e.target.value.toUpperCase())}
          placeholder="e.g., RELIANCE, TCS, INFY…"
          disabled={loading}
          className="flex-1 bg-slate-900 border border-slate-600 rounded-lg px-4 py-2.5 text-sm placeholder-slate-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 disabled:opacity-50"
        />
        <button
          type="submit"
          disabled={loading || !symbol.trim()}
          className="bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed px-6 py-2.5 rounded-lg text-sm font-medium transition-colors"
        >
          {loading ? "Analysing…" : "Analyse"}
        </button>
      </form>

      <div className="flex flex-wrap gap-2 mt-4">
        {POPULAR.map((s) => (
          <button
            key={s}
            onClick={() => { setSymbol(s); onSearch(s); }}
            disabled={loading}
            className="text-xs bg-slate-700 hover:bg-slate-600 disabled:opacity-40 px-3 py-1 rounded-full transition-colors text-slate-300"
          >
            {s}
          </button>
        ))}
      </div>
    </div>
  );
}
