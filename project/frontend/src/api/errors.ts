import axios from "axios";

const MAX_USER_MSG_LEN = 520;

function clampUserMessage(msg: string): string {
  const t = msg.trim();
  if (t.length <= MAX_USER_MSG_LEN) return t;
  return `${t.slice(0, MAX_USER_MSG_LEN)}…`;
}

/** FastAPI / axios hatalarından kısa kullanıcı mesajı (çok uzun gövde kesilir). */
export function formatApiError(err: unknown, fallback: string): string {
  if (!axios.isAxiosError(err)) {
    return clampUserMessage(err instanceof Error ? err.message : fallback);
  }
  const status = err.response?.status;
  const data = err.response?.data;
  if (data == null) {
    return clampUserMessage(status ? `${fallback} (HTTP ${status})` : fallback);
  }
  if (typeof data === "string") {
    return clampUserMessage(data);
  }
  if (typeof data === "object" && data !== null && "detail" in data) {
    const d = (data as { detail: unknown }).detail;
    if (typeof d === "string") return clampUserMessage(d);
    if (Array.isArray(d)) {
      return clampUserMessage(
        d.map((x) => (typeof x === "object" && x && "msg" in x ? String((x as { msg: unknown }).msg) : String(x))).join("; "),
      );
    }
    if (typeof d === "object" && d !== null && "message" in d) {
      return clampUserMessage(String((d as { message: unknown }).message));
    }
  }
  return clampUserMessage(status ? `${fallback} (HTTP ${status})` : fallback);
}
