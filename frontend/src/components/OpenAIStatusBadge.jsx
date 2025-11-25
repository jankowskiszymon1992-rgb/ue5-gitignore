import { useEffect, useRef, useState } from "react";

export default function OpenAIStatusBadge() {
  const [state, setState] = useState({ label: "Sprawdzam…", tone: "muted", raw: null, at: null });
  const dlgRef = useRef(null);
  const keyRef = useRef("");
  const timerRef = useRef(null);
  const nextDelayRef = useRef(5000);
  const lastToneRef = useRef(null);

  const classify = (p) => {
    if (!p) return { label: "Błąd połączenia", tone: "error" };
    if (p.ok === true) return { label: "OpenAI: OK", tone: "ok" };
    if (p.error === "missing_key") return { label: "OpenAI: brak klucza", tone: "warn" };
    if (p.status === 401 || /incorrect api key/i.test(p?.body || "")) return { label: "OpenAI: zły klucz", tone: "error" };
    return { label: "OpenAI: problem", tone: "warn" };
  };

  const plan = (ms) => { clearTimeout(timerRef.current); timerRef.current = setTimeout(pull, ms); };

  const pull = async () => {
    try {
      const r = await fetch("/api/openai/status", { cache: "no-store" });
      const json = await r.json().catch(() => null);
      const c = classify(json);
      setState({ label: c.label, tone: c.tone, raw: json, at: new Date() });
      window.dispatchEvent(new CustomEvent("openai-status", { detail: { tone: c.tone, label: c.label, raw: json } }));
      nextDelayRef.current = c.tone === "ok" ? 30000 : Math.min((nextDelayRef.current || 5000) * 2, 60000);
      plan(nextDelayRef.current);
    } catch {
      setState({ label: "Błąd połączenia", tone: "error", raw: null, at: new Date() });
      window.dispatchEvent(new CustomEvent("openai-status", { detail: { tone: "error", label: "Błąd połączenia", raw: null } }));
      nextDelayRef.current = Math.min((nextDelayRef.current || 5000) * 2, 60000);
      plan(nextDelayRef.current);
    }
  };

  useEffect(() => { pull(); return () => clearTimeout(timerRef.current); }, []);

  const dot = { ok: "bg-green-500", warn: "bg-amber-500", error: "bg-red-500", muted: "bg-zinc-400" }[state.tone || "muted"];
  const atText = state.at ? new Intl.DateTimeFormat(undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit" }).format(state.at) : "";

  const copy = async (txt) => { try { await navigator.clipboard.writeText(txt); } catch { prompt("Skopiuj:", txt); } };

  return (
    <>
      <div className="inline-flex items-center gap-2 text-xs px-2 py-1 rounded-md border">
        <span className={`inline-block w-2 h-2 rounded-full ${dot}`} />
        <span>{state.label}</span>
        {atText && <span className="opacity-60">· {atText}</span>}
        <button onClick={() => { nextDelayRef.current = 5000; pull(); }} className="ml-2 underline">Odśwież</button>
        <button onClick={() => dlgRef.current?.showModal()} className="ml-1 underline">Ustaw klucz</button>
      </div>

      <dialog ref={dlgRef} className="rounded-md p-0 w-[min(90vw,640px)]">
        <form method="dialog">
          <div className="p-4 border-b">
            <div className="text-lg font-semibold">Ustaw klucz OpenAI</div>
            <div className="text-sm opacity-70">Pole jest <b>lokalne</b> – służy do wygenerowania komend. Klucz <b>nie</b> jest wysyłany.</div>
          </div>
          <div className="p-4 space-y-3">
            <label className="text-sm">Klucz OpenAI</label>
            <input type="text" placeholder="sk-..." onChange={(e) => (keyRef.current = e.target.value)} className="mt-1 w-full border rounded px-2 py-1" />
            <div className="flex flex-wrap gap-2">
              <button type="button" className="px-3 py-1 border rounded"
                onClick={() => copy(`export OPENAI_API_KEY=${keyRef.current}\ndocker compose -f docker-compose.simple.yml up -d --build`)}>
                Kopiuj export + compose
              </button>
              <button type="button" className="px-3 py-1 border rounded" onClick={() => copy(`OPENAI_API_KEY=${keyRef.current}`)}>
                Kopiuj dla panelu env
              </button>
              <button type="button" className="px-3 py-1 border rounded" onClick={() => copy(`curl -s http://localhost/api/openai/status | jq .`)}>
                Kopiuj curl
              </button>
              <button type="button" className="px-3 py-1 border rounded" onClick={() => { nextDelayRef.current = 5000; pull(); }}>
                Testuj teraz
              </button>
            </div>
            <details className="text-xs">
              <summary className="cursor-pointer">Surowy wynik</summary>
              <pre className="mt-2 p-2 bg-zinc-100 rounded overflow-auto">{state.raw ? JSON.stringify(state.raw, null, 2) : "(brak danych)"}</pre>
            </details>
          </div>
          <div className="p-3 border-t flex justify-end">
            <button className="px-3 py-1 border rounded">Zamknij</button>
          </div>
        </form>
      </dialog>
    </>
  );
}