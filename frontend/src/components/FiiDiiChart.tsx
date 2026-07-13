import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ReferenceLine,
  ResponsiveContainer,
} from "recharts";
import type { FiiDiiEntry } from "../types";

interface Props {
  data: FiiDiiEntry[];
}

const FMT = (v: number) =>
  new Intl.NumberFormat("en-IN", {
    maximumFractionDigits: 0,
    signDisplay: "exceptZero",
  }).format(v);

export default function FiiDiiChart({ data }: Props) {
  if (!data || data.length === 0) {
    return (
      <div className="bg-slate-800 rounded-xl border border-slate-700 p-6">
        <h3 className="font-semibold text-sm text-slate-200 mb-2">FII / DII Activity</h3>
        <p className="text-slate-500 text-sm">NSE data unavailable at this time.</p>
      </div>
    );
  }

  const chartData = data.map((d) => ({
    date: d.date.replace(/^\d{4}-/, "").replace(/-/g, "/"), // short date
    FII: d.fii_net,
    DII: d.dii_net,
  }));

  // Net totals
  const totalFii = data.reduce((s, d) => s + d.fii_net, 0);
  const totalDii = data.reduce((s, d) => s + d.dii_net, 0);

  return (
    <div className="bg-slate-800 rounded-xl border border-slate-700 p-6">
      <div className="flex flex-wrap items-center justify-between gap-4 mb-4">
        <h3 className="font-semibold text-sm text-slate-200">FII / DII Net Activity (₹ Crores)</h3>
        <div className="flex gap-4 text-xs">
          <span className={totalFii >= 0 ? "text-emerald-400" : "text-red-400"}>
            FII Net: {FMT(totalFii)}Cr
          </span>
          <span className={totalDii >= 0 ? "text-emerald-400" : "text-red-400"}>
            DII Net: {FMT(totalDii)}Cr
          </span>
        </div>
      </div>

      <ResponsiveContainer width="100%" height={250}>
        <BarChart data={chartData} margin={{ top: 4, right: 8, left: 8, bottom: 4 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
          <XAxis
            dataKey="date"
            tick={{ fill: "#64748b", fontSize: 10 }}
            interval="preserveStartEnd"
          />
          <YAxis
            tick={{ fill: "#64748b", fontSize: 10 }}
            tickFormatter={(v) => `${(v / 1000).toFixed(0)}K`}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: "#1e293b",
              border: "1px solid #334155",
              borderRadius: "8px",
              fontSize: "12px",
            }}
            labelStyle={{ color: "#f1f5f9" }}
            formatter={(value: number) => [`₹${FMT(value)}Cr`, ""]}
          />
          <Legend
            wrapperStyle={{ fontSize: "11px", color: "#94a3b8" }}
          />
          <ReferenceLine y={0} stroke="#475569" strokeWidth={1} />
          <Bar dataKey="FII" name="FII Net" fill="#6366f1" radius={[2, 2, 0, 0]} />
          <Bar dataKey="DII" name="DII Net" fill="#10b981" radius={[2, 2, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
