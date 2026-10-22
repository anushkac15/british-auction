import { useMutation } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";

import { useCurrentUser } from "../hooks/useCurrentUser";

export function Login() {
  const { login } = useCurrentUser();
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: string } | null)?.from ?? "/";
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  const mutation = useMutation({
    mutationFn: () => login({ email, password }),
    onSuccess: () => navigate(from, { replace: true }),
  });

  function submit(e: FormEvent) {
    e.preventDefault();
    mutation.mutate();
  }

  return (
    <section className="auth-page">
      <form className="card form auth-card" onSubmit={submit}>
        <h1>Log in</h1>
        <p className="muted">Buyers and suppliers sign in here. Your account type decides what you can do.</p>
        <label>
          Email
          <input type="email" autoComplete="email" required autoFocus value={email} onChange={(e) => setEmail(e.target.value)} />
        </label>
        <label>
          Password
          <input
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </label>
        {mutation.error && <div className="error">{mutation.error.message}</div>}
        <button type="submit" disabled={mutation.isPending}>
          {mutation.isPending ? "Logging in…" : "Log in"}
        </button>
        <p className="muted small auth-switch">
          New here? <Link to="/register">Register as a buyer or supplier</Link>
        </p>
      </form>
    </section>
  );
}
