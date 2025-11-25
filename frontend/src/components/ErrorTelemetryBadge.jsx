import React, { useEffect, useRef, useState } from "react";

function ymUTC(d=new Date()){ const y=d.getUTCFullYear(); const m=String(d.getUTCMonth()+1).padStart(2,"0"); return `${y}-${m}`; }

export default function ErrorTelemetryBadge(){
  const [count,setCount]=useState(0);
  const [open,setOpen]=useState(false);
  const [rows,setRows]=useState([]);
  const timerRef=useRef(null);

  const load=async()=>{
    try{
      const r=await fetch(`/api/usage/errors?month=${ymUTC()}`,{cache:"no-store"});
      const j=await r.json();
      setCount(j.count||0); setRows(j.items||[]);
    }catch{/**/}
  };

  useEffect(()=>{
    load(); timerRef.current=setInterval(load,30000);
    return ()=>clearInterval(timerRef.current);
  },[]);

  // prosty globalny catcher (włączany localStorage.telemetry="1")
  useEffect(()=>{
    const enable = localStorage.getItem("telemetry")==="1";
    if(!enable) return;
    const onErr=(ev)=>{
      try{ fetch("/api/usage/error",{method:"POST",headers:{"Content-Type":"application/json"},
        body: JSON.stringify({message:String(ev?.message||"window.onerror"), where:"frontend", detail:{source:"onerror"}})}); }catch{}
    };
    const onRej=(ev)=>{
      try{ fetch("/api/usage/error",{method:"POST",headers:{"Content-Type":"application/json"},
        body: JSON.stringify({message:String(ev?.reason?.message||"unhandledrejection"), where:"frontend", detail:{source:"unhandledrejection"}})}); }catch{}
    };
    window.addEventListener("error",onErr);
    window.addEventListener("unhandledrejection",onRej);
    return ()=>{ window.removeEventListener("error",onErr); window.removeEventListener("unhandledrejection",onRej); };
  },[]);

  const sendTest=async()=>{
    await fetch("/api/usage/error",{method:"POST",headers:{"Content-Type":"application/json"},
      body: JSON.stringify({message:"Test error", where:"frontend", detail:{btn:"clicked"}})});
    load();
  };

  return (
    <>
      <div className="inline-flex items-center gap-2 text-xs px-2 py-1 rounded-md border">
        <span className={`inline-block w-2 h-2 rounded-full ${count>0?"bg-amber-500":"bg-green-500"}`} />
        <span>Errors: {count}</span>
        <button onClick={sendTest} className="ml-2 underline">Wyślij test</button>
        <button onClick={()=>setOpen(true)} className="ml-1 underline">Podgląd</button>
      </div>

      {open && (
        <dialog open className="rounded-md p-0 w-[min(90vw,720px)]">
          <form method="dialog">
            <div className="p-3 border-b flex items-center justify-between">
              <div className="text-lg font-semibold">Ostatnie błędy ({count})</div>
              <button className="px-2 py-1 border rounded text-sm" onClick={()=>setOpen(false)}>Zamknij</button>
            </div>
            <div className="p-3">
              <div className="overflow-x-auto border rounded">
                <table className="min-w-full text-sm">
                  <thead><tr className="bg-zinc-100">
                    <th className="text-left px-2 py-1">Czas</th>
                    <th className="text-left px-2 py-1">Wiadomość</th>
                    <th className="text-left px-2 py-1">Gdzie</th>
                  </tr></thead>
                  <tbody>
                    {rows.length===0 ? (
                      <tr><td className="px-2 py-2 opacity-60" colSpan={3}>Brak błędów</td></tr>
                    ) : rows.map((r,i)=>(
                      <tr key={i} className="border-t">
                        <td className="px-2 py-1">{r.ts}</td>
                        <td className="px-2 py-1">{r.message}</td>
                        <td className="px-2 py-1">{r.where}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </form>
        </dialog>
      )}
    </>
  );
}