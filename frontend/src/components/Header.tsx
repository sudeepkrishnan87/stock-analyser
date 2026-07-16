type Tab = "research" | "signals";

interface Props {
  isAuthenticated: boolean;
  onTokenSetup: () => void;
  onLogout: () => void;
  activeTab: Tab;
  onTabChange: (tab: Tab) => void;
  pendingSignalCount: number;
}

export default function Header({
  isAuthenticated,
  onTokenSetup,
  onLogout,
  activeTab,
  onTabChange,
  pendingSignalCount,
}: Props) {
  return (
    <header className="bg-slate-900 border-b border-slate-800 sticky top-0 z-40">
      <div className="max-w-7xl mx-auto px-4 py-3 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 bg-indigo-600 rounded-lg flex items-center justify-center font-bold text-sm">
            J
          </div>
          <div>
            <h1 className="font-bold text-lg leading-none">Jarvis</h1>
            <p className="text-slate-500 text-xs">Indian Markets · Elliott Wave · AI</p>
          </div>

          <nav className="flex items-center gap-1 ml-4 bg-slate-800/60 rounded-lg p-1">
            <button
              onClick={() => onTabChange("research")}
              className={`text-xs font-medium px-3 py-1.5 rounded-md transition-colors ${
                activeTab === "research"
                  ? "bg-slate-700 text-slate-100"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              Research
            </button>
            <button
              onClick={() => onTabChange("signals")}
              className={`relative flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-md transition-colors ${
                activeTab === "signals"
                  ? "bg-slate-700 text-slate-100"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9" />
                <path d="M10.3 21a1.94 1.94 0 0 0 3.4 0" />
              </svg>
              Signals
              {pendingSignalCount > 0 && (
                <span className="absolute -top-1.5 -right-1.5 flex items-center justify-center min-w-[16px] h-4 px-1 rounded-full bg-amber-500 text-slate-950 text-[10px] font-bold leading-none animate-pulse">
                  {pendingSignalCount > 9 ? "9+" : pendingSignalCount}
                </span>
              )}
            </button>
          </nav>
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

          {!isAuthenticated && (
            <button
              onClick={onTokenSetup}
              className="text-xs bg-indigo-600 hover:bg-indigo-500 px-3 py-1.5 rounded-lg transition-colors"
            >
              Connect Kite
            </button>
          )}

          <button
            onClick={onLogout}
            title="Lock / Sign out"
            className="text-slate-500 hover:text-slate-300 transition-colors p-1.5 rounded-lg hover:bg-slate-800"
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <rect width="11" height="11" x="1" y="11" rx="2" ry="2"/>
              <path d="M7 11V7a5 5 0 0 1 9.9-1"/>
            </svg>
          </button>
        </div>
      </div>
    </header>
  );
}
