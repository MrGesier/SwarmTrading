export const API = (import.meta.env.VITE_API_URL ?? "").replace(/\/$/, "");

export function wsUrl(path: string): string {
  if (API) {
    const u = new URL(API);
    const protocol = u.protocol === "https:" ? "wss:" : "ws:";
    return `${protocol}//${u.host}${path}`;
  }
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${window.location.host}${path}`;
}
