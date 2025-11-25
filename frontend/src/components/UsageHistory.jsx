import React, { useEffect, useMemo, useState } from "react";
import { utils as XLSXUtils, writeFile as writeXLSX } from "xlsx";

function fmtDate(d){ const y=d.getUTCFullYear(); const m=String(d.getUTCMonth()+1).padStart(2,"0"); const day=String(d.getUTCDate()).padStart(2,"0"); return `${y}-${m}-${day}`; }
function firstOfMonthUTC(d=new Date()){ return new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), 1)); }
function todayUTC(){ const d=new Date(); return new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate())); }

export default function UsageHistory(){
  const [from,setFrom] = useState(fmtDate(firstOfMonthUTC()));
  const [to,setTo]     = useState(fmtDate(todayUTC()));
  const [source,setSource]=useState("");
  const [page,setPage]=useState(1);
  const [pageSize,setPageSize]=useState(20);
  const [rows,setRows]=useState([]);
  const [total,setTotal]=useState(0);
  const [pages,setPages]=useState(1);
  const [loading,setLoading]=useState(false);
  const [sort,setSort]=useState("desc");

  const q = () => {
    const p = new URLSearchParams();
    if (from) p.set("from", from);
    if (to) p.set("to", to);
    if (source) p.set("source", source);
    p.set("page", String(page));
    p.set("page_size", String(pageSize));
    p.set("sort", sort);
    return p.toString();
  };

  const load = async() => {
    setLoading(true);
    try {
      const r = await fetch(`/api/usage/list?${q()}`, { cache: "no-store" });
      const j = await r.json();
      setRows(j.items || []);
      setTotal(j.total || 0);
      setPages(j.pages || 1);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  };

  useEffect(()=>{ setPage(1); }, [from,to,source,pageSize,sort]);
  useEffect(()=>{ load(); }, [page,from,to,source,pageSize,sort]);

  const csv = useMemo(()=>{
    const head=["ts","minutes","source"];
    const lines=[head.join(",")];
    (rows||[]).forEach(r=>{
      lines.push([r.ts, r.minutes, r.source].map(x=>String(x).replaceAll('"','""')).map(x=>`"${x}"`).join(","));
    });
    return lines.join("\n");
  },[rows]);

  const exportCSVPage = () => {
    const blob=new Blob([csv],{type:"text/csv;charset=utf-8"});
    const a=document.createElement("a");
    a.href=URL.createObjectURL(blob);
    a.download=`usage_${from}_${to}${source?`_${source}`:""}_p${page}.csv`;
    a.click(); URL.revokeObjectURL(a.href);
  };

  const exportXLSXPage = () => {
    const ws = XLSXUtils.json_to_sheet(rows || []);
    const wb = XLSXUtils.book_new();
    XLSXUtils.book_append_sheet(wb, ws, "Usage");
    writeXLSX(wb, `usage_${from}_${to}${source?`_${source}`:""}_p${page}.xlsx`);
  };

  const exportAll = async (fmt="csv") => {
    const limit = 5000; // safety cap
    const p = new URLSearchParams();
    if (from) p.set("from", from); if (to) p.set("to", to); if (source) p.set("source", source);
    p.set("page", "1"); p.set("page_size", String(limit)); p.set("sort", sort);
    const r = await fetch(`/api/usage/list?${p.toString()}`, { cache: "no-store" });
    const j = await r.json();
    const data = j.items || [];
    if (fmt === "csv") {
      const head=["ts","minutes","source"];
      const lines=[head.join(",")];
      data.forEach(r=>lines.push([r.ts,r.minutes,r.source].map(x=>String(x).replaceAll('"','""')).map(x=>`"${x}"`).join(",")));
      const blob=new Blob([lines.join("\n")],{type:"text/csv;charset=utf-8"});
      const a=document.createElement("a"); a.href=URL.createObjectURL(blob);
      a.download=`usage_${from}_${to}${source?`_${source}`:""}_ALL.csv`; a.click(); URL.revokeObjectURL(a.href);
    } else {
      const ws = XLSXUtils.json_to_sheet(data);
      const wb = XLSXUtils.book_new();
      XLSXUtils.book_append_sheet(wb, ws, "Usage");
      writeXLSX(wb, `usage_${from}_${to}${source?`_${source}`:""}_ALL.xlsx`);
    }
  };

  const canPrev = page > 1;
  const canNext = page < pages;

  return (
    <section className="mt-8">
      <div className="flex flex-wrap items-end gap-2 mb-3">
        <h2 className="text-lg font-semibold">Historia zużycia</h2>
        <span className="text-xs opacity-60">({total} rekordów)</span>
        <div className="flex-1" />
        <div className="flex items-center gap-2">
          <label className="text-xs">Od</label>
          <input type="date" value={from} onChange={e=>setFrom(e.target.value)} className="border rounded px-2 py-1 text-sm" />
          <label className="text-xs">Do</label>
          <input type="date" value={to} onChange={e=>setTo(e.target.value)} className="border rounded px-2 py-1 text-sm" />
          <select value={source} onChange={e=>setSource(e.target.value)} className="border rounded px-2 py-1 text-sm">
            <option value="">Źródło: wszystkie</option>
            <option value="voice">voice</option>
            <option value="manual">manual</option>
            <option value="import">import</option>
          </select>
          <select value={sort} onChange={e=>setSort(e.target.value)} className="border rounded px-2 py-1 text-sm">
            <option value="desc">Najnowsze ↓</option>
            <option value="asc">Najstarsze ↑</option>
          </select>
          <select value={pageSize} onChange={e=>setPageSize(Number(e.target.value))} className="border rounded px-2 py-1 text-sm">
            <option value="10">10 / str.</option>
            <option value="20">20 / str.</option>
            <option value="50">50 / str.</option>
            <option value="100">100 / str.</option>
          </select>
          <button onClick={()=>{setPage(1); load();}} className="px-2 py-1 border rounded text-sm">Odśwież</button>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2 mb-2">
        <button onClick={exportCSVPage} className="px-2 py-1 border rounded text-sm">Eksport CSV (ta strona)</button>
        <button onClick={exportXLSXPage} className="px-2 py-1 border rounded text-sm">Eksport XLSX (ta strona)</button>
        <button onClick={()=>exportAll("csv")} className="px-2 py-1 border rounded text-sm">Eksport CSV (wszystko)</button>
        <button onClick={()=>exportAll("xlsx")} className="px-2 py-1 border rounded text-sm">Eksport XLSX (wszystko)</button>
        <div className="flex-1" />
        <div className="text-xs opacity-70">Strona {page} z {pages}</div>
        <button disabled={!canPrev} onClick={()=>setPage(p=>Math.max(1,p-1))} className="px-2 py-1 border rounded text-sm disabled:opacity-50">« Prev</button>
        <button disabled={!canNext} onClick={()=>setPage(p=>Math.min(pages,p+1))} className="px-2 py-1 border rounded text-sm disabled:opacity-50">Next »</button>
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
            ) : (rows||[]).length===0 ? (
              <tr><td className="px-2 py-2 opacity-60" colSpan={3}>Brak danych</td></tr>
            ) : (rows||[]).map((r,i)=>(
              <tr key={i} className="border-t">
                <td className="px-2 py-1">{r.ts}</td>
                <td className="px-2 py-1 text-right">{Number(r.minutes??0).toFixed(3)}</td>
                <td className="px-2 py-1">{r.source}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}