import React, { useRef, useState, useEffect } from "react";
import { recordUsage, startUsageQueue } from "../lib/offlineQueue";

/**
 * Jeden komponent + jeden export default.
 * - Tryb MOCK: localStorage.voice_mock === "1" lub VITE_VOICE_MOCK=1 (domyślnie ON dla demo).
 * - Safari fallback: audio/mp4 jeśli webm nieobsługiwany.
 * - Raport minut: przez offlineQueue → /api/usage/add (nie gubi danych).
 */
export default function VoiceChatPanel({ onTranscription, disabled }) {
  const [isRecording, setIsRecording] = useState(false);
  const [isSending, setIsSending] = useState(false);
  const [error, setError] = useState("");
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [mockOn, setMockOn] = useState(() => {
    const ls = localStorage.getItem("voice_mock");
    if (ls === "1" || ls === "0") return ls === "1";
    return (import.meta?.env?.VITE_VOICE_MOCK ?? "0") === "1";
  });

  const mediaRecorderRef = useRef(null);
  const chunksRef = useRef([]);
  const timerRef = useRef(null);
  const mimeRef = useRef({ mimeType: "", ext: "webm" });

  useEffect(() => { startUsageQueue(); }, []);
  useEffect(() => {
    if (isRecording) {
      setElapsedSeconds(0);
      timerRef.current = setInterval(() => setElapsedSeconds((p) => p + 1), 1000);
    } else if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    return () => { if (timerRef.current) clearInterval(timerRef.current); };
  }, [isRecording]);

  const formatTime = (s) => `${String(Math.floor(s/60)).padStart(2,"0")}:${String(s%60).padStart(2,"0")}`;

  const pickMime = () => {
    const list = ["audio/webm;codecs=opus","audio/webm","audio/mp4","audio/aac"];
    for (const t of list) {
      try { if (typeof MediaRecorder !== "undefined" && MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported(t)) {
        if (t.includes("mp4")) return { mimeType: t, ext: "m4a" };
        if (t.includes("aac")) return { mimeType: t, ext: "aac" };
        return { mimeType: t, ext: "webm" };
      } } catch {}
    }
    return { mimeType: "", ext: "webm" };
  };

  const doMockSend = async () => {
    setIsSending(true);
    await new Promise((r) => setTimeout(r, 300));
    const text = "test transkrypcji (mock)";
    if (typeof onTranscription === "function") onTranscription(text);
    setIsSending(false);
  };

  const handleToggleRecording = async () => {
    if (disabled || isSending) return;
    setError("");

    // STOP
    if (isRecording) {
      try { const rec = mediaRecorderRef.current; if (rec && rec.state !== "inactive") rec.stop(); }
      catch (e) { console.error("Stop MediaRecorder:", e); }
      finally {
        setIsRecording(false);
        // why: raportuj faktyczny czas nagrania (odporne na offline/rate-limit)
        try { await recordUsage(elapsedSeconds || 0, "voice"); } catch {}
      }
      return;
    }

    // START
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });

      if (mockOn) {
        mediaRecorderRef.current = { state: "recording", stop: async () => {
          await doMockSend();
        }};
        setIsRecording(true);
        return;
      }

      const { mimeType, ext } = pickMime();
      mimeRef.current = { mimeType, ext };
      const rec = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
      chunksRef.current = [];

      rec.ondataavailable = (e) => { if (e.data && e.data.size > 0) chunksRef.current.push(e.data); };

      rec.onstop = async () => {
        try {
          const finalType = mimeRef.current.mimeType || "audio/webm";
          const finalExt = mimeRef.current.ext || "webm";
          const blob = new Blob(chunksRef.current, { type: finalType });
          chunksRef.current = [];
          stream.getTracks().forEach((t) => t.stop());

          setIsSending(true);
          const formData = new FormData();
          formData.append("file", blob, `voice-message.${finalExt}`);

          const backendBase = (import.meta?.env?.VITE_API_BASE || "").replace(/\/$/,"");
          const url = (backendBase || "/api") + "/voice/transcribe";
          const response = await fetch(url, { method: "POST", body: formData });

          if (!response.ok) {
            let msg = `Błąd transkrypcji (${response.status})`;
            try { const j = await response.json(); if (j?.detail) msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail); } catch {}
            setError(msg); setIsSending(false);
          } else {
            const data = await response.json();
            const text = data?.text || "(brak tekstu)";
            if (typeof onTranscription === "function") onTranscription(text);
            setIsSending(false);
          }
        } catch (err) {
          console.error("Wysyłka nagrania:", err);
          setError("Wystąpił problem podczas wysyłania nagrania.");
          setIsSending(false);
        }
      };

      mediaRecorderRef.current = rec;
      rec.start();
      setIsRecording(true);
    } catch (err) {
      console.error("Dostęp do mikrofonu:", err);
      if (err?.name === "NotAllowedError") setError("Brak zgody na mikrofon. Sprawdź ustawienia przeglądarki.");
      else if (err?.name === "NotFoundError") setError("Nie wykryto mikrofonu.");
      else setError("Nie udało się uruchomić nagrywania.");
      setIsRecording(false);
    }
  };

  const toggleMock = () => {
    const next = !mockOn;
    setMockOn(next);
    localStorage.setItem("voice_mock", next ? "1" : "0");
  };

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-3">
        <button type="button" onClick={handleToggleRecording} disabled={disabled || isSending}
          className={`inline-flex items-center justify-center px-3 py-2 rounded-full border text-sm font-medium transition
            ${isRecording ? "bg-red-600 border-red-400 text-white" : "bg-zinc-900 border-zinc-700 text-zinc-100 hover:bg-zinc-800"}
            ${disabled || isSending ? "opacity-60 cursor-not-allowed" : ""}`}>
          <span className={`inline-block w-2.5 h-2.5 rounded-full mr-2 ${isRecording ? "bg-red-300 animate-pulse" : "bg-zinc-400"}`} />
          {isRecording ? "Nagrywam – kliknij, aby zakończyć" : (mockOn ? "Nagraj (MOCK)" : "Nagraj wiadomość głosową")}
        </button>
        {isRecording && <span className="text-xs text-red-300">Czas: {formatTime(elapsedSeconds)}</span>}
        {isSending &&   <span className="text-xs text-amber-300">Wysyłam nagranie…</span>}
        <button type="button" onClick={toggleMock}
          className={`ml-2 text-xs px-2 py-1 rounded border ${mockOn ? "bg-yellow-600 text-white border-yellow-500" : "bg-zinc-800 text-zinc-100 border-zinc-700"}`}>
          MOCK: {mockOn ? "ON" : "OFF"}
        </button>
      </div>
      {error && <div className="text-xs text-red-400">{error}</div>}
    </div>
  );
}