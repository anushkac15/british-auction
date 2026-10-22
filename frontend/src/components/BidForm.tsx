import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { ApiError, api } from "../api/client";
import type { BidResponse, RfqDetail } from "../api/types";
import { formatMoney, formatTime, isMoney, sumMoney, toCents } from "../lib/format";

interface Props {
  rfq: RfqDetail;
}

export function BidForm({ rfq }: Props) {
  const queryClient = useQueryClient();
  const myLatest = rfq.ranking.find((r) => r.is_me)?.quote;
  const [values, setValues] = useState({
    carrier_name: myLatest?.carrier_name ?? "",
    freight_charges: "",
    origin_charges: "",
    destination_charges: "",
    transit_time_days: myLatest ? String(myLatest.transit_time_days) : "",
    quote_validity_date: myLatest?.quote_validity_date ?? rfq.pickup_date,
  });
  const [clientError, setClientError] = useState<string | null>(null);
  const [result, setResult] = useState<BidResponse | null>(null);

  const total = sumMoney([values.freight_charges, values.origin_charges, values.destination_charges]);
  const set = (key: keyof typeof values) => (e: { target: { value: string } }) =>
    setValues((v) => ({ ...v, [key]: e.target.value }));

  const mutation = useMutation({
    mutationFn: () =>
      api.placeBid(rfq.id, {
        carrier_name: values.carrier_name.trim(),
        freight_charges: values.freight_charges.trim(),
        origin_charges: values.origin_charges.trim(),
        destination_charges: values.destination_charges.trim(),
        transit_time_days: Number(values.transit_time_days),
        quote_validity_date: values.quote_validity_date,
      }),
    onSuccess: (res) => {
      setResult(res);
      setValues((v) => ({ ...v, freight_charges: "", origin_charges: "", destination_charges: "" }));
      void queryClient.invalidateQueries({ queryKey: ["rfq", rfq.id] });
      void queryClient.invalidateQueries({ queryKey: ["rfqs"] });
    },
  });

  function validate(): string | null {
    if (!values.carrier_name.trim()) return "Carrier name is required";
    for (const key of ["freight_charges", "origin_charges", "destination_charges"] as const) {
      if (!isMoney(values[key])) return "Charges must be non-negative amounts with at most 2 decimals";
    }
    if (!/^\d+$/.test(values.transit_time_days) || Number(values.transit_time_days) <= 0)
      return "Transit time must be a positive whole number of days";
    if (!values.quote_validity_date || values.quote_validity_date < rfq.pickup_date)
      return "Quote must be valid until at least the pickup date";
    if (total !== null && rfq.my_best_bid !== null && toCents(total) >= toCents(rfq.my_best_bid))
      return `Total must be lower than your previous bid (${formatMoney(rfq.my_best_bid)})`;
    return null;
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    setResult(null);
    const err = validate();
    setClientError(err);
    if (!err) mutation.mutate();
  }

  const serverError = mutation.error instanceof ApiError ? mutation.error.message : mutation.error?.message;

  return (
    <form className="card form" onSubmit={submit} noValidate>
      <h3>Submit a quote</h3>
      <p className="muted small">
        {rfq.my_best_bid
          ? `Your current bid: ${formatMoney(rfq.my_best_bid)} (L${rfq.my_rank}). Each new bid must be lower.`
          : "You have not bid yet."}{" "}
        {rfq.lowest_bid && `Current L1: ${formatMoney(rfq.lowest_bid)}.`}
      </p>
      <div className="grid-2">
        <label>
          Carrier name
          <input value={values.carrier_name} onChange={set("carrier_name")} maxLength={120} />
        </label>
        <label>
          Transit time (days)
          <input value={values.transit_time_days} onChange={set("transit_time_days")} inputMode="numeric" />
        </label>
        <label>
          Freight charges
          <input value={values.freight_charges} onChange={set("freight_charges")} inputMode="decimal" placeholder="0.00" />
        </label>
        <label>
          Origin charges
          <input value={values.origin_charges} onChange={set("origin_charges")} inputMode="decimal" placeholder="0.00" />
        </label>
        <label>
          Destination charges
          <input
            value={values.destination_charges}
            onChange={set("destination_charges")}
            inputMode="decimal"
            placeholder="0.00"
          />
        </label>
        <label>
          Quote valid until
          <input type="date" value={values.quote_validity_date} min={rfq.pickup_date} onChange={set("quote_validity_date")} />
        </label>
      </div>
      <div className="form-footer">
        <div>
          Total: <strong>{total ? formatMoney(total) : "—"}</strong>
        </div>
        <button type="submit" disabled={mutation.isPending}>
          {mutation.isPending ? "Submitting…" : "Place bid"}
        </button>
      </div>
      {(clientError || serverError) && <div className="error">{clientError ?? serverError}</div>}
      {result && (
        <div className="success">
          Bid accepted: you are L{result.rank} of {result.participant_count}.
          {result.extension &&
            ` Auction extended to ${formatTime(result.extension.new_close_at)}${result.extension.capped ? " (forced close reached)" : ""}.`}
        </div>
      )}
    </form>
  );
}
