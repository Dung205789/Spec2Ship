"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { apiGet, apiPost, API_BASE } from "../lib/api";

function StatusPill({ status }) {
  const s = (status || "").toLowerCase();
  let cls = "pill";
  if (s === "completed") cls += " ok";
  else if (s.includes("fail") || s === "canceled") cls += " bad";
  else if (s.includes("wait")) cls += " wait";
  else if (s === "running" || s === "queued") cls += " run";
  return <span className={cls}>{status || "unknown"}</span>;
}

export default function RunsPage() {
  const [runs, setRuns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");

  async function refresh() {
    setLoading(true);
    setErr("");
    try {
      const data = await apiGet("/runs/");
      setRuns(Array.isArray(data) ? data : []);
    } catch (e) {
      setErr(e?.message || String(e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 4000);
    return () => clearInterval(t);
  }, []);

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 20 }}>
        <div>
          <h1 style={{ fontSize: 20, fontWeight: 700 }}>All Runs</h1>
          <div style={{ fontSize: 13, color: "var(--text-muted)", marginTop: 2 }}>Auto-refreshes every 4 seconds</div>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button className="btn btn-ghost" onClick={refresh} disabled={loading}>Refresh</button>
          <Link href="/" className="btn btn-primary">+ New run</Link>
        </div>
      </div>

      {err && <div className="alert error" style={{ marginBottom: 12 }}>{err}</div>}

      <div className="card">
        {loading && runs.length === 0 ? (
          <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "32px", color: "var(--text-muted)", fontSize: 13 }}>
            <div className="spinner" /> Loading…
          </div>
        ) : runs.length === 0 ? (
          <div className="empty-state">
            <div className="icon">🚀</div>
            <div style={{ fontSize: 14 }}>No runs yet. <Link href="/" style={{ color: "var(--accent)" }}>Create your first run →</Link></div>
          </div>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Title</th>
                <th>Status</th>
                <th>Workspace</th>
                <th>Created</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {runs.map((r) => (
                <tr key={r.id}>
                  <td style={{ fontWeight: 500 }}>{r.title}</td>
                  <td><StatusPill status={r.status} /></td>
                  <td style={{ color: "var(--text-muted)", fontSize: 12 }}>{r.workspace || "—"}</td>
                  <td style={{ color: "var(--text-muted)", fontSize: 12 }}>
                    {r.created_at ? new Date(r.created_at).toLocaleString() : "—"}
                  </td>
                  <td>
                    <Link className="btn btn-ghost" href={`/runs/${r.id}`} style={{ padding: "5px 10px", fontSize: 12 }}>Open →</Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
