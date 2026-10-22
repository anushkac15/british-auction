import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";

import { ApiError, api } from "../api/client";
import type { TriggerType } from "../api/types";
import { useCurrentUser } from "../hooks/useCurrentUser";
import { serverNow } from "../hooks/serverClock";
import { TRIGGER_LABEL } from "../lib/format";
import {
  MAX_EXTENSION_MINUTES,
  MAX_WINDOW_MINUTES,
  toCreateInput,
  toLocalDate,
  toLocalInput,
  validateCreate,
  type CreateFormValues,
  type FormErrors,
} from "../lib/validation";

const MIN = 60_000;

function defaults(): CreateFormValues {
  const now = serverNow();
  const start = Math.ceil((now + 5 * MIN) / MIN) * MIN;
  const stamp = new Date(now).toISOString().replace(/[-:T]/g, "").slice(0, 12);
  return {
    reference_id: `RFQ-${stamp}`,
    name: "",
    pickup_date: toLocalDate(start + 2 * 24 * 60 * MIN),
    bid_start_at: toLocalInput(start),
    bid_close_at: toLocalInput(start + 30 * MIN),
    forced_close_at: toLocalInput(start + 60 * MIN),
    trigger_window_minutes: "10",
    extension_minutes: "5",
    trigger_type: "ANY_RANK_CHANGE",
  };
}

export function CreateRfq() {
  const { user } = useCurrentUser();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [values, setValues] = useState<CreateFormValues>(defaults);
  const [errors, setErrors] = useState<FormErrors>({});

  const mutation = useMutation({
    mutationFn: () => api.createRfq(toCreateInput(values)),
    onSuccess: (res) => {
      void queryClient.invalidateQueries({ queryKey: ["rfqs"] });
      navigate(`/rfqs/${res.rfq.id}`);
    },
    onError: (err) => {
      if (err instanceof ApiError && err.field) setErrors({ [err.field]: err.message });
    },
  });

  if (user && user.role !== "BUYER") {
    return (
      <div className="card">
        Only buyers can create RFQs. Log in with a buyer account to create one. <Link to="/">Back to auctions</Link>
      </div>
    );
  }

  const set = (key: keyof CreateFormValues) => (e: { target: { value: string } }) =>
    setValues((v) => ({ ...v, [key]: e.target.value }));

  function submit(e: FormEvent) {
    e.preventDefault();
    const found = validateCreate(values, serverNow());
    setErrors(found);
    if (Object.keys(found).length === 0) mutation.mutate();
  }

  const field = (key: keyof CreateFormValues, label: string, input: JSX.Element, hint?: string) => (
    <label className={errors[key] ? "invalid" : ""}>
      {label}
      {input}
      {errors[key] ? <span className="field-error">{errors[key]}</span> : hint && <span className="muted small">{hint}</span>}
    </label>
  );

  const serverError = mutation.error && !(mutation.error instanceof ApiError && mutation.error.field) ? mutation.error.message : null;

  return (
    <section>
      <div className="page-header">
        <div>
          <h1>Create RFQ</h1>
          <p className="muted">British Auction is enabled for every RFQ. Times are in your local time zone.</p>
        </div>
      </div>
      <form className="card form" onSubmit={submit} noValidate>
        <h3>RFQ details</h3>
        <div className="grid-2">
          {field("reference_id", "RFQ reference ID", <input value={values.reference_id} onChange={set("reference_id")} maxLength={50} />)}
          {field("name", "RFQ name", <input value={values.name} onChange={set("name")} placeholder="e.g. Mumbai → Delhi FTL" maxLength={200} />)}
          {field("bid_start_at", "Bid start", <input type="datetime-local" value={values.bid_start_at} onChange={set("bid_start_at")} />, "Must be in the future")}
          {field("bid_close_at", "Bid close", <input type="datetime-local" value={values.bid_close_at} onChange={set("bid_close_at")} />, "Can be extended by the auction rules")}
          {field("forced_close_at", "Forced bid close", <input type="datetime-local" value={values.forced_close_at} onChange={set("forced_close_at")} />, "Hard stop; must be after bid close")}
          {field("pickup_date", "Pickup / service date", <input type="date" value={values.pickup_date} onChange={set("pickup_date")} />, "On or after the forced close date")}
        </div>

        <h3>British Auction configuration</h3>
        <div className="grid-3">
          {field(
            "trigger_window_minutes",
            "Trigger window X (min)",
            <input type="number" min={1} max={MAX_WINDOW_MINUTES} value={values.trigger_window_minutes} onChange={set("trigger_window_minutes")} />,
            `Monitor the last X minutes (1–${MAX_WINDOW_MINUTES})`,
          )}
          {field(
            "extension_minutes",
            "Extension Y (min)",
            <input type="number" min={1} max={MAX_EXTENSION_MINUTES} value={values.extension_minutes} onChange={set("extension_minutes")} />,
            `Add Y minutes when triggered (1–${MAX_EXTENSION_MINUTES})`,
          )}
          {field(
            "trigger_type",
            "Extension trigger",
            <select value={values.trigger_type} onChange={(e) => setValues((v) => ({ ...v, trigger_type: e.target.value as TriggerType }))}>
              {(Object.keys(TRIGGER_LABEL) as TriggerType[]).map((t) => (
                <option key={t} value={t}>
                  {TRIGGER_LABEL[t]}
                </option>
              ))}
            </select>,
          )}
        </div>

        {serverError && <div className="error">{serverError}</div>}
        <div className="form-footer">
          <Link to="/">Cancel</Link>
          <button type="submit" disabled={mutation.isPending}>
            {mutation.isPending ? "Creating…" : "Create RFQ"}
          </button>
        </div>
      </form>
    </section>
  );
}
