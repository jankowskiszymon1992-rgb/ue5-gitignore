/**
 * Offline queue dla /api/usage/add — trzyma w localStorage i flushuje co 15 s oraz przy 'online'.
 * why: nie gubimy metryk przy braku sieci / 429.
 */
const KEY = "usage_queue_v1";

function loadQ() {
  try { return JSON.parse(localStorage.getItem(KEY) || "[]"); } catch { return []; }
}
function saveQ(arr) {
  try { localStorage.setItem(KEY, JSON.stringify(arr.slice(0, 2000))); } catch {}
}

export async function recordUsage(seconds, source = "voice") {
  const minutes = (seconds || 0) / 60;
  if (!Number.isFinite(minutes) || minutes <= 0) return;
  try {
    const res = await fetch("/api/usage/add", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ minutes, source })
    });
    if (res.status === 429) throw new Error("rate_limited");
    if (!res.ok) throw new Error("bad_status");
  } catch {
    const q = loadQ(); q.push({ minutes, source, ts: Date.now() }); saveQ(q);
  }
}

export async function flushUsageQueue() {
  let q = loadQ();
  if (!q.length) return;
  const keep = [];
  for (const item of q) {
    try {
      const res = await fetch("/api/usage/add", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ minutes: item.minutes, source: item.source })
      });
      if (res.status === 429) throw new Error("rate_limited");
      if (!res.ok) throw new Error("bad_status");
    } catch {
      keep.push(item);
    }
  }
  saveQ(keep);
}

let _timer;
export function startUsageQueue() {
  if (typeof window !== "undefined") {
    window.addEventListener("online", flushUsageQueue);
    clearInterval(_timer);
    _timer = setInterval(flushUsageQueue, 15000);
  }
}

export function stopUsageQueue() {
  if (typeof window !== "undefined") {
    window.removeEventListener("online", flushUsageQueue);
    clearInterval(_timer);
  }
}
