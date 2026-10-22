import { Link } from "react-router-dom";

import { useCurrentUser } from "../hooks/useCurrentUser";

export function UserMenu() {
  const { user, logout } = useCurrentUser();
  if (!user) {
    return (
      <nav className="user-menu">
        <Link to="/login">Log in</Link>
        <Link to="/register" className="button">
          Register
        </Link>
      </nav>
    );
  }
  return (
    <div className="user-menu">
      <span>
        {user.name} <span className="muted">· {user.role === "BUYER" ? "Buyer" : "Supplier"}</span>
      </span>
      <button type="button" className="secondary" onClick={logout}>
        Log out
      </button>
    </div>
  );
}
