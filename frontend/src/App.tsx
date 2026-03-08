import { Link, Navigate, Route, Routes, useParams } from "react-router-dom";
import { UploadReviewPage } from "./pages/UploadReviewPage";
import { RoundsPage } from "./pages/RoundsPage";
import { RoundDetailPage } from "./pages/RoundDetailPage";
import { RoundEditPage } from "./pages/RoundEditPage";
import { AnalyticsPage } from "./pages/AnalyticsPage";

const isStaticMode = import.meta.env.VITE_USE_STATIC_DATA === "true";

function RedirectToRoundDetail() {
  const { id } = useParams<{ id: string }>();
  return <Navigate to={`/rounds/${id}`} replace />;
}

export function App() {
  return (
    <div style={{ minHeight: "100vh", display: "flex", flexDirection: "column", fontFamily: "system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif" }}>
      <header style={{ padding: "1rem 2rem", borderBottom: "1px solid #e5e7eb", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div style={{ fontWeight: 600 }}>Golf Sim Stats</div>
        <nav style={{ display: "flex", gap: "1rem", fontSize: "0.95rem" }}>
          {!isStaticMode && <Link to="/">Upload &amp; Review</Link>}
          <Link to="/rounds">Rounds</Link>
          <Link to="/analytics">Analytics</Link>
        </nav>
      </header>
      <main style={{ flex: 1, padding: "1.5rem 2rem", backgroundColor: "#f9fafb" }}>
        <Routes>
          <Route path="/" element={isStaticMode ? <Navigate to="/rounds" replace /> : <UploadReviewPage />} />
          <Route path="/rounds" element={<RoundsPage />} />
          <Route path="/rounds/:id/edit" element={isStaticMode ? <RedirectToRoundDetail /> : <RoundEditPage />} />
          <Route path="/rounds/:id" element={<RoundDetailPage />} />
          <Route path="/analytics" element={<AnalyticsPage />} />
        </Routes>
      </main>
    </div>
  );
}

