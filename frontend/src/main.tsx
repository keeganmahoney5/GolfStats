import React, { useEffect, useState } from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { App } from "./App";
import { setStaticData } from "./staticData";
import type { ShareData } from "./staticData";

const isStaticMode = import.meta.env.VITE_USE_STATIC_DATA === "true";
const baseUrl = import.meta.env.BASE_URL || "/";

function ShareBootstrap({ children }: { children: React.ReactNode }) {
  const [loading, setLoading] = useState(isStaticMode);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isStaticMode) return;
    const url = `${baseUrl}share-data.json`;
    fetch(url)
      .then((r) => {
        if (!r.ok) throw new Error(`Failed to load: ${r.status}`);
        return r.json() as Promise<ShareData>;
      })
      .then((data) => {
        setStaticData(data);
        setLoading(false);
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : "Failed to load data");
        setLoading(false);
      });
  }, []);

  if (isStaticMode && loading) {
    return (
      <div style={{ padding: "2rem", textAlign: "center", fontFamily: "system-ui, sans-serif" }}>
        Loading…
      </div>
    );
  }
  if (isStaticMode && error) {
    return (
      <div style={{ padding: "2rem", textAlign: "center", fontFamily: "system-ui, sans-serif", color: "#dc2626" }}>
        Failed to load data: {error}
      </div>
    );
  }
  return <>{children}</>;
}

const rootElement = document.getElementById("root");

if (rootElement) {
  const root = ReactDOM.createRoot(rootElement);
  root.render(
    <React.StrictMode>
      <BrowserRouter basename={baseUrl.replace(/\/$/, "") || "/"}>
        <ShareBootstrap>
          <App />
        </ShareBootstrap>
      </BrowserRouter>
    </React.StrictMode>
  );
}

