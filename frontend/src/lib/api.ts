// frontend/src/lib/api.ts
const BASE = process.env.REACT_APP_API_BASE; // or import.meta.env.VITE_API_BASE (Vite)

export async function predict(payload: any) {
  const res = await fetch(`${BASE}/predict`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}
