const base = "";

function headers(extra={}) {
  const h = { "Content-Type": "application/json", ...extra };
  const t = localStorage.getItem("token");
  return t ? { ...h, "Authorization": `Bearer ${t}` } : h;
}

export default {
  async get(url) {
    const r = await fetch(url, { headers: headers({}), cache: "no-store" });
    if (!r.ok) throw new Error(`GET ${url} ${r.status}`);
    return { data: await r.json() };
  },
  async post(url, data) {
    const r = await fetch(url, { method: "POST", headers: headers(), body: JSON.stringify(data) });
    if (!r.ok) throw new Error(`POST ${url} ${r.status}`);
    return { data: await r.json() };
  },
  async patch(url, data) {
    const r = await fetch(url, { method: "PATCH", headers: headers(), body: JSON.stringify(data) });
    if (!r.ok) throw new Error(`PATCH ${url} ${r.status}`);
    return { data: await r.json() };
  },
  async delete(url) {
    const r = await fetch(url, { method: "DELETE", headers: headers() });
    if (!r.ok) throw new Error(`DELETE ${url} ${r.status}`);
    return { data: await r.json() };
  }
};