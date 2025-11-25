import { useEffect, useRef, useState } from "react";

export default function CostBadge() {
  const [data, setData] = useState({ minutes: 0, from: "", to: "" });
  const rate = Number.parseFloat(import.meta?.env?.VITE_OPENAI_RATE ?? "0.006"); // $/min
  const pln = Number.parseFloat(import.meta?.env?.VITE_PLN_RATE ?? "4");       // PLN/USD
  const timerRef = useRef(null);

  const ym = () => {
    const d = new Date(); const y = d.getUTCFullYear(); const m = String(d.getUTCMonth() + 1).padStart(2, "0");
    return `${y}-${m}`;
  };

  const pull = async () => {
    try {
      const r = await fetch(`/api/usage/stats?month=${ym()}`, { cache: "no-store" });
      const j = await r.json();
      setData({ minutes: j.minutes || 0, from: j.from || "", to: j.to || "" });
    } catch { /* ignore */ }
  };

  useEffect(() => { pull(); timerRef.current = setInterval(pull, 30000); return () => clearInterval(timerRef.current); }, []);
  const usd = data.minutes * rate; const PLN = usd * pln;

  return (
    <div className="inline-flex items-center gap-2 text-xs px-2 py-1 rounded-md border">
      <span className="inline-block w-2 h-2 rounded-full bg-zinc-400" />
      <span>{data.minutes.toFixed(0)} min</span>
      <span className="opacity-60">· ${usd.toFixed(2)} (~{PLN.toFixed(0)} zł)</span>
      <button onClick={pull} className="ml-2 underline">Odśwież</button>
    </div>
  );
}