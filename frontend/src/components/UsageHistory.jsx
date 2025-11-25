import React, { useEffect, useMemo, useState } from "react";

function ymUTC(d=new Date()){ const y=d.getUTCFullYear(); const m=String(d.getUTCMonth()+1).padStart(2,"0"); return `${y}-${m}`; }

export default function UsageHistory(){
  const [month,setMonth]=useState(ymUTC());
  const [source,setSource]=useState("");
  const [rows,setRows]=useState([]);
  const [count,setCount]=useState(0);
  const [loading,setLoading]=useState(false);

  const load=async()=>{
    setLoading(true);
    try{
      const q=new URLSearchParams({month, ...(source?{source}:{})}).toString();
      const r=await fetch(`/api/usage/list?${q}`,{cache:"no-store"});
      const j=await r.json();
      setRows(j.items||[]); setCount(j.count||0);
    }catch{/**/}finally{setLoading(false);}
  };
  useEffect(()=>{ load(); },[month,source]);

  const csv=useMemo(()=>{
    const head=["ts","minutes","source"];
    const lines=[head.join(",")];
    (rows||[]).forEach(r=>{
      lines.push([r.ts, r.minutes, r.source].map(x=>String(x).replaceAll('"','""')).map(x=>`"${x}"`).join(","));
    });
    return lines.join("\n");
  },[rows]);

  const downloadCSV=()=>{
    const blob=new Blob([csv],{type:"text/csv;charset=utf-8"});
    const a=document.createElement("a");
    a.href=URL.createObjectURL(blob);
    a.download=`usage_${month}${source?`_${source}`:""}.csv`;
    a.click();
    URL.revokeObjectURL(a.href);
  };

  return (
    <section className="mt-8">
      <div className="flex items-center gap-2 mb-3">
        <h2 className="text-lg font-semibold">Historia zużycia</h2>
        <span className="text-xs opacity-60">({count} rekordów)</span>
        <div className="flex-1" />
        <input type="month" value={month} onChange={e=>setMonth(e.target.value)} className="border rounded px-2 py-1 text-sm" />
        <select value={source} onChange={e=>setSource(e.target.value)} className="border rounded px-2 py-1 text-sm">
          <option value="">Wszystkie źródła</option>
          <option value="voice">voice</option>
          <option value="manual">manual</option>
          <option value="import">import</option>
        </select>
        <button onClick={load} className="px-2 py-1 border rounded text-sm">Odśwież</button>
        <button onClick={downloadCSV} className="px-2 py-1 border rounded text-sm">Eksport CSV</button>
      </div>

      <div className="overflow-x-auto border rounded">
        <table className="min-w-full text-sm">
          <thead>
            <tr className="bg-zinc-100">
              <th className="text-left px-2 py-1">Czas (UTC)</th>
              <th className="text-right px-2 py-1">Minuty</th>
              <th className="text-left px-2 py-1">Źródło</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td className="px-2 py-2 opacity-60" colSpan={3}>Ładowanie…</td></tr>
            ) : rows.length===0 ? (
              <tr><td className="px-2 py-2 opacity-60" colSpan={3}>Brak danych</td></tr>
            ) : rows.map((r,i)=>(
              <tr key={i} className="border-t">
                <td className="px-2 py-1">{r.ts}</td>
                <td className="px-2 py-1 text-right">{(r.minutes??0).toFixed(3)}</td>
                <td className="px-2 py-1">{r.source}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}