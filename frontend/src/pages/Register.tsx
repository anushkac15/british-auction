import { useMutation } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { ApiError } from "../api/client";
import type { Role } from "../api/types";
import { useCurrentUser } from "../hooks/useCurrentUser";

const MIN_PASSWORD_LENGTH = 8;
const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

const ROLES: { value: Role; title: string; description: string }[] = [
  { value: "BUYER", title: "Buyer", description: "Create RFQs and watch suppliers compete in British Auctions." },
  { value: "SUPPLIER", title: "Supplier", description: "Bid on open RFQs and track your rank live." },
];

interface Values {
  name: string;
  email: string;
  password: string;
  confirm: string;
  role: Role;
}

type Errors = Partial<Record<keyof Values, string>>;

function validate(v: Values): Errors {
  const errors: Errors = {};
  if (!v.name.trim()) errors.name = "Enter your company or display name";
  if (!EMAIL_RE.test(v.email.trim())) errors.email = "Enter a valid email address";
  if (v.password.length < MIN_PASSWORD_LENGTH) errors.password = `Use at least ${MIN_PASSWORD_LENGTH} characters`;
  if (v.confirm !== v.password) errors.confirm = "Passwords don't match";
  return errors;
}

export function Register() {
  const { register } = useCurrentUser();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [values, setValues] = useState<Values>(() => ({
    name: "",
    email: "",
    password: "",
    confirm: "",
    role: params.get("role")?.toUpperCase() === "SUPPLIER" ? "SUPPLIER" : "BUYER",
  }));
  const [errors, setErrors] = useState<Errors>({});

  const mutation = useMutation({
    mutationFn: () =>
      register({ name: values.name.trim(), email: values.email.trim(), password: values.password, role: values.role }),
    onSuccess: () => navigate("/", { replace: true }),
    onError: (err) => {
      if (!(err instanceof ApiError)) return;
      const found: Errors = {};
      for (const e of err.errors) if (e.field && e.field in values) found[e.field as keyof Values] = e.message;
      if (err.field && err.field in values) found[err.field as keyof Values] = err.message;
      setErrors(found);
    },
  });

  const set = (key: keyof Values) => (e: { target: { value: string } }) =>
    setValues((v) => ({ ...v, [key]: e.target.value }));

  function submit(e: FormEvent) {
    e.preventDefault();
    const found = validate(values);
    setErrors(found);
    if (Object.keys(found).length === 0) mutation.mutate();
  }

  const field = (key: keyof Values, label: string, input: JSX.Element) => (
    <label className={errors[key] ? "invalid" : ""}>
      {label}
      {input}
      {errors[key] && <span className="field-error">{errors[key]}</span>}
    </label>
  );

  const serverError =
    mutation.error && !(mutation.error instanceof ApiError && (mutation.error.field || mutation.error.errors.length))
      ? mutation.error.message
      : null;

  return (
    <section className="auth-page">
      <form className="card form auth-card" onSubmit={submit} noValidate>
        <h1>Create an account</h1>
        <p className="muted">Choose how you'll use the platform. This can't be changed later.</p>

        <div className="role-options" role="radiogroup" aria-label="Account type">
          {ROLES.map((r) => (
            <label key={r.value} className={`role-option${values.role === r.value ? " selected" : ""}`}>
              <input
                type="radio"
                name="role"
                value={r.value}
                checked={values.role === r.value}
                onChange={() => setValues((v) => ({ ...v, role: r.value }))}
              />
              <span className="strong">I'm a {r.title.toLowerCase()}</span>
              <span className="muted small">{r.description}</span>
            </label>
          ))}
        </div>

        {field(
          "name",
          values.role === "BUYER" ? "Company name" : "Supplier / company name",
          <input value={values.name} onChange={set("name")} maxLength={120} autoComplete="organization" />,
        )}
        {field("email", "Email", <input type="email" value={values.email} onChange={set("email")} maxLength={200} autoComplete="email" />)}
        <div className="grid-2">
          {field(
            "password",
            "Password",
            <input type="password" value={values.password} onChange={set("password")} maxLength={128} autoComplete="new-password" />,
          )}
          {field(
            "confirm",
            "Confirm password",
            <input type="password" value={values.confirm} onChange={set("confirm")} maxLength={128} autoComplete="new-password" />,
          )}
        </div>

        {serverError && <div className="error">{serverError}</div>}
        <button type="submit" disabled={mutation.isPending}>
          {mutation.isPending ? "Creating account…" : `Register as ${values.role === "BUYER" ? "buyer" : "supplier"}`}
        </button>
        <p className="muted small auth-switch">
          Already have an account? <Link to="/login">Log in</Link>
        </p>
      </form>
    </section>
  );
}
