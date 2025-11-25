import React, { useEffect, useRef, useState } from "react";
import OpenAIStatusBadge from "./OpenAIStatusBadge";
import CostBadge from "./CostBadge";

export default function AppHeader({ onAdd }) {
  const searchRef = useRef(null);
  const [banner, setBanner] = useState({ show: false, tone: "ok", label: "" });

  useEffect(() => {
    const h = (e) => {
      const { tone, label } = (e.detail || {});
      const show = tone === "error" || tone === "warn";
      setBanner({ show, tone: tone || "ok", label: label || "" });
    };
    window.addEventListener("openai-status", h);
    return () => window.removeEventListener("openai-status", h);
  }, []);

  useEffect(() => {
    const onSlash = (e) => {
      if (e.key === "/" && !e.metaKey && !e.ctrlKey && !e.altKey) {
        e.preventDefault(); searchRef.current?.focus();
      }
    };
    window.addEventListener("keydown", onSlash);
    return () => window.removeEventListener("keydown", onSlash);
  }, []);

  return (
    <>
      <header style={{position:"sticky",top:0,zIndex:30,backdropFilter:"blur(6px)"}}
              className="w-full border-b bg-white/80 dark:bg-zinc-900/80">
        <div className="max-w-screen-xl mx-auto flex items-center gap-2 p-3">
          <div className="text-lg font-semibold">🍓 Raspberry App</div>
          <div className="flex-1" />
          <input ref={searchRef} placeholder="Szukaj… (/)"
                 className="w-full max-w-xs border rounded px-2 py-1 text-sm" />
          <div className="ml-2"><OpenAIStatusBadge /></div>
          <div className="ml-2"><CostBadge /></div>
          {onAdd && <button className="ml-2 px-3 py-1 border rounded text-sm" onClick={onAdd}>Dodaj wpis</button>}
        </div>
        {banner.show && (
          <div role="alert"
               className={["w-full text-xs px-3 py-2 text-white",
                           banner.tone==="error"?"bg-red-600":"bg-amber-600"].join(" ")}>
            <div className="max-w-screen-xl mx-auto">
              <b>Status OpenAI:</b> {banner.label}. Wejdź w „Ustaw klucz" na górze.
            </div>
          </div>
        )}
      </header>
    </>
  );
}