import { formatDateTime, formatDuration } from "../lib/format";

interface Props {
  label: string;
  target: string;
  nowMs: number;
  doneLabel?: string;
  note?: string;
  highlight?: boolean;
}

export function Countdown({ label, target, nowMs, doneLabel = "Ended", note, highlight }: Props) {
  const remaining = Date.parse(target) - nowMs;
  const urgent = remaining > 0 && remaining <= 60_000;
  return (
    <div className={`card countdown ${urgent ? "urgent" : ""} ${highlight ? "highlight" : ""}`}>
      <div className="muted small">{label}</div>
      <div className="countdown-value">{remaining > 0 ? formatDuration(remaining) : doneLabel}</div>
      <div className="small">{formatDateTime(target)}</div>
      {note && <div className="muted small">{note}</div>}
    </div>
  );
}
