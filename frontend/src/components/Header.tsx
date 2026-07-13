interface Props {
  isAuthenticated: boolean;
  onTokenSetup: () => void;
}

export default function Header({ isAuthenticated, onTokenSetup }: Props) {
  return (
    <header className="bg-slate-900 border-b border-slate-800 sticky top-0 z-40">
      <div className="max-w-7xl mx-auto px-4 py-3 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 bg-indigo-600 rounded-lg flex items-center justify-center font-bold text-sm">
            AI
          </div>
          <div>
            <h1 className="font-bold text-lg leading-none">Stock Analyser</h1>
            <p className="text-slate-500 text-xs">Indian Markets · Elliott Wave · AI</p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <div className={`flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-full border ${
            isAuthenticated
              ? "bg-emerald-900/30 text-emerald-400 border-emerald-700/50"
              : "bg-slate-800 text-slate-400 border-slate-700"
          }`}>
            <div className={`w-1.5 h-1.5 rounded-full ${isAuthenticated ? "bg-emerald-400" : "bg-slate-500"}`} />
            {isAuthenticated ? "Kite Connected" : "Not Connected"}
          </div>
          <button
            onClick={onTokenSetup}
            className="text-xs bg-indigo-600 hover:bg-indigo-500 px-3 py-1.5 rounded-lg transition-colors"
          >
            {isAuthenticated ? "Re-auth" : "Setup Token"}
          </button>
        </div>
      </div>
    </header>
  );
}
