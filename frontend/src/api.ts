// frontend/src/api.ts
export async function getHello() {
  const base = import.meta.env.VITE_API_BASE_URL; // 例: https://xxx.onrender.com
  const r = await fetch(`${base}/api/hello`);
  if (!r.ok) throw new Error("API error");
  return r.json();
}
