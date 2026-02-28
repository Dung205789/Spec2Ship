const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
export const API_BASE = API;

export async function apiGet(path) {
  const res = await fetch(`${API}${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function apiPost(path, body) {
  const res = await fetch(`${API}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : null,
    cache: "no-store",
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function apiPostForm(path, formData) {
  const res = await fetch(`${API}${path}`, {
    method: "POST",
    body: formData,
    cache: "no-store",
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function apiGetText(path, params) {
  const url = new URL(`${API}${path}`);
  Object.entries(params || {}).forEach(([k,v]) => url.searchParams.set(k, v));
  const res = await fetch(url.toString(), { cache: "no-store" });
  if (!res.ok) throw new Error(await res.text());
  return res.text();
}
