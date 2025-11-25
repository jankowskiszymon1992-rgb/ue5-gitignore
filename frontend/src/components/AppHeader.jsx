import OpenAIStatusBadge from "./OpenAIStatusBadge";
import CostBadge from "./CostBadge";
import { useEffect, useRef, useState } from "react";

export default function AppHeader() {
  const searchRef = useRef(null);
  const [banner, setBanner] = useState({ show: false, tone: "ok", label: "" });

  useEffect(() => {
    const onStatus = (e) => {
      const { tone, label } = e.detail || {};
      const show = tone === "warn" || tone === "error";
      setBanner({ show, tone: tone || "ok", label: label || "" });
    };
    window.addEventListener("openai-status", onStatus);
    return () => window.removeEventListener("openai-status", onStatus);
  }, []);

  useEffect(() => {
    const h = (e) => { if (e.key === "/" && !e.metaKey && !e.ctrlKey && !e.altKey) { e.preventDefault(); searchRef.current?.focus(); } };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, []);

  return (
    <>
      <header style={{ position: "sticky", top: 0, zIndex: 30, backdropFilter: "blur(6px)" }} className="w-full border-b bg-white/80">
        <div className="max-w-screen-xl mx-auto flex items-center gap-2 p-3">
          <div className="text-lg font-semibold">🍓 raspberry-app</div>
          <div className="flex-1" />
          <input ref={searchRef} placeholder="Szukaj… (/)" className="w-full max-w-xs border rounded px-2 py-1 text-sm" />
          <div className="ml-2"><OpenAIStatusBadge /></div>
          <div className="ml-2"><CostBadge /></div>
        </div>
        {banner.show && (
          <div role="alert" className={`w-full text-xs px-3 py-2 text-white ${banner.tone === "error" ? "bg-red-600" : "bg-amber-600"}`}>
            <div className="max-w-screen-xl mx-auto"><b>Status OpenAI:</b> {banner.label}. Ustaw klucz w dialogu u góry.</div>
          </div>
        )}
      </header>
    </>
  );
}