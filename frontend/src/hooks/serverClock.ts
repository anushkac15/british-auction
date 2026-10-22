import { useEffect, useState } from "react";

// Offset between the server clock and this browser's clock, in milliseconds.
// Countdowns use Date.now() + offset so a skewed browser clock doesn't mislead bidders.
let offsetMs = 0;
let calibrated = false;

export function updateServerClock(serverNowIso: string, requestStartMs: number, responseEndMs: number) {
  const serverMs = Date.parse(serverNowIso);
  if (Number.isNaN(serverMs)) return;
  // Assume the server stamped the response halfway through the round trip.
  const midpoint = (requestStartMs + responseEndMs) / 2;
  const sample = serverMs - midpoint;
  // Smooth small jitter, but jump immediately on the first sample or a large correction.
  offsetMs = !calibrated || Math.abs(sample - offsetMs) > 2000 ? sample : offsetMs * 0.7 + sample * 0.3;
  calibrated = true;
}

export function serverNow(): number {
  return Date.now() + offsetMs;
}

export function serverOffsetMs(): number {
  return offsetMs;
}

/** Re-renders every `intervalMs` with the current server-corrected time (epoch ms). */
export function useServerNow(intervalMs = 1000): number {
  const [now, setNow] = useState(serverNow);
  useEffect(() => {
    const id = window.setInterval(() => setNow(serverNow()), intervalMs);
    return () => window.clearInterval(id);
  }, [intervalMs]);
  return now;
}
