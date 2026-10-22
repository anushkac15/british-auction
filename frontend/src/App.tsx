import { Link, Navigate, Route, Routes, useLocation } from "react-router-dom";

import { UserMenu } from "./components/UserMenu";
import { useCurrentUser } from "./hooks/useCurrentUser";
import { AuctionDetail } from "./pages/AuctionDetail";
import { AuctionList } from "./pages/AuctionList";
import { CreateRfq } from "./pages/CreateRfq";
import { Login } from "./pages/Login";
import { Register } from "./pages/Register";

export function App() {
  const { loading, error, user } = useCurrentUser();
  const location = useLocation();
  return (
    <>
      <header className="topbar">
        <Link to="/" className="brand">
          British Auction <span className="muted">RFQ</span>
        </Link>
        {!loading && <UserMenu />}
      </header>
      <main className="container">
        {loading && <p className="muted">Connecting…</p>}
        {error && <div className="error">Cannot reach the API: {error.message}</div>}
        {!loading && !error && user && (
          <Routes>
            <Route path="/" element={<AuctionList />} />
            <Route path="/rfqs/new" element={<CreateRfq />} />
            <Route path="/rfqs/:id" element={<AuctionDetail />} />
            <Route path="/login" element={<Navigate to="/" replace />} />
            <Route path="/register" element={<Navigate to="/" replace />} />
            <Route path="*" element={<p>Page not found.</p>} />
          </Routes>
        )}
        {!loading && !error && !user && (
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route path="/register" element={<Register />} />
            <Route path="*" element={<Navigate to="/login" replace state={{ from: location.pathname }} />} />
          </Routes>
        )}
      </main>
    </>
  );
}
