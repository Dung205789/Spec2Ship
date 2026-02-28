"use client";

import { useEffect, useMemo, useState, useCallback } from "react";
import Link from "next/link";
import { apiGet, apiGetText, apiPost, API_BASE } from "../../lib/api";

function StatusPill({ status }) {
  const s = (status || "").toLowerCase();
  let cls = "pill";
  if (s === "completed") cls += " ok";
  else if (s.includes("fail") || s === "canceled") cls += " bad";
  else if (s.includes("wait")) cls += " wait";
  else if (s === "running" || s === "queued") cls += " run";
  else cls += " default";
  return <span className={cls}>{status || "—"}</span>;
}

function StepIcon({ status }) {
  const map = {
    success: { icon: "✓", cls: "success" },
    failed: { icon: "✕", cls: "failed" },
    waiting: { icon: "⏸", cls: "waiting" },
    running: { icon: "⟳", cls: "running" },
    skipped: { icon: "→", cls: "skipped" },
    pending: { icon: "·", cls: "pending" },
  };
  const { icon, cls } = map[status] || { icon: "·", cls: "pending" };
  return <span className={`step-icon ${cls}`}>{icon}</span>;
}

function DiffView({ text }) {
  if (!text) return <pre style={{ padding: 16, color: "var(--text-muted)" }}>(empty)</pre>;
  const lines = text.split("\n");
  return (
    <pre style={{ padding: 16, margin: 0 }}>
      {lines.map((line, i) => {
        let cls = "";
        if (line.startsWith("+") && !line.startsWith("+++")) cls = "diff-line-add";
        else if (line.startsWith("-") && !line.startsWith("---")) cls = "diff-line-del";
        else if (line.startsWith("@@")) cls = "diff-line-hunk";
        return cls
          ? <span key={i} className={cls}>{line + "\n"}</span>
          : <span key={i} style={{ color: "#6b7fa0" }}>{line + "\n"}</span>;
      })}
    </pre>
  );
}

function SignalChips({ signals }) {
  if (!signals?.length) return null;
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 8 }}>
      {signals.map((s, i) => (
        <span key={i} className={`signal-chip ${s.kind === "test_failure" || s.kind === "syntax" || s.kind === "runtime" ? "error" : "warning"}`}>
          {s.kind === "test_failure" ? "✕" : s.kind === "syntax" ? "⚠" : "◆"} {s.summary}
        </span>
      ))}
    </div>
  );
}

const TOTAL_STEPS = 11;

export default function RunDetail({ params }) {
  const id = params.id;
  const [run, setRun] = useState(null);
  const [steps, setSteps] = useState([]);
  const [artifacts, setArtifacts] = useState([]);
  const [selectedArtifact, setSelectedArtifact] = useState(null);
  const [artifactText, setArtifactText] = useState("");
  const [artifactLoading, setArtifactLoading] = useState(false);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [actionMsg, setActionMsg] = useState("");
  const [signals, setSignals] = useState([]);

  const refresh = useCallback(async () => {
    try {
      const [r, s, a] = await Promise.all([
        apiGet(`/runs/${id}`),
        apiGet(`/runs/${id}/steps`),
        apiGet(`/runs/${id}/artifacts`),
      ]);
      setRun(r);
      setSteps(Array.isArray(s) ? s : []);
      setArtifacts(Array.isArray(a) ? a : []);
    } catch (e) {
      setErr(e?.message || String(e));
    }
  }, [id]);

  const refreshSignals = useCallback(async () => {
    try {
      const data = await apiGet(`/runs/${id}/signals`);
      if (data?.signals) setSignals(data.signals);
    } catch {}
  }, [id]);

  useEffect(() => {
    refresh();
    refreshSignals();
    const t = setInterval(() => { refresh(); refreshSignals(); }, 2000);
    return () => clearInterval(t);
  }, [refresh, refreshSignals]);

  useEffect(() => {
    if (!selectedArtifact?.path) { setArtifactText(""); return; }
    setArtifactLoading(true);
    setArtifactText("");
    apiGetText("/artifacts/text", { path: selectedArtifact.path })
      .then(setArtifactText)
      .catch((e) => setArtifactText(`Failed to load: ${e?.message}`))
      .finally(() => setArtifactLoading(false));
  }, [selectedArtifact?.path]);

  const doneCount = useMemo(() => steps.filter((s) => s.status === "success" || s.status === "skipped").length, [steps]);
  const progress = TOTAL_STEPS > 0 ? Math.round((doneCount / TOTAL_STEPS) * 100) : 0;

  const canStart = run && ["created", "failed", "canceled", "completed"].includes(run.status);
  const isActive = run && ["running", "queued"].includes(run.status);
  const waitingApproval = run?.status === "waiting_approval";

  const proposeStep = useMemo(() => steps.find((s) => s.name?.toLowerCase() === "propose patch"), [steps]);
  const applyStep = useMemo(() => steps.find((s) => s.name?.toLowerCase() === "apply patch"), [steps]);
  const postStep = useMemo(() => steps.find((s) => s.name?.toLowerCase().includes("re-run")), [steps]);
  const hasInvalidPatch = artifacts.some((a) => a.kind === "invalid_patch");
  const hasNextActions = artifacts.some((a) => a.kind === "next_actions");
  const canRegenerate = proposeStep?.status === "failed" || applyStep?.status === "failed" || postStep?.status === "failed" || hasInvalidPatch || hasNextActions;
  const reportDone = steps.some((s) => s.name?.toLowerCase().includes("report") && s.status === "success");
  const isCompleted = run?.status === "completed";
  const isFailed = run?.status === "failed";

  const diffArtifact = artifacts.find((a) => a.kind === "proposal_diff");
  const reportArtifact = artifacts.find((a) => a.kind === "report");

  async function action(fn, successMsg) {
    setBusy(true); setErr(""); setActionMsg("");
    try { await fn(); setActionMsg(successMsg || "Done"); await refresh(); }
    catch (e) { setErr(e?.message || String(e)); }
    finally { setBusy(false); }
  }

  const start = () => action(() => apiPost(`/runs/${id}/start`), "Pipeline started ⚡");
  const retry = () => action(() => apiPost(`/runs/${id}/retry`), "Full retry queued ↺");
  const cancelRun = () => action(() => apiPost(`/runs/${id}/cancel`), "Run canceled");
  const approve = () => action(() => apiPost(`/runs/${id}/patch_decision?decision=yes`), "Patch approved — continuing ✓");
  const reject = () => action(() => apiPost(`/runs/${id}/patch_decision?decision=rejected`), "Patch rejected");
  const regenerate = () => action(
    () => apiPost(`/runs/${id}/regenerate_patch`),
    "Regenerating patch 🔄 (workspace reset to clean state)"
  );

  async function deleteRun() {
    if (!confirm("Delete this run and all its artifacts?")) return;
    setBusy(true);
    try {
      const res = await fetch(`${API_BASE}/runs/${id}`, { method: "DELETE" });
      if (!res.ok) throw new Error(await res.text());
      window.location.href = "/";
    } catch (e) { setErr(e?.message || String(e)); setBusy(false); }
  }

  // Auto-select key artifacts
  useEffect(() => {
    if (waitingApproval && diffArtifact && !selectedArtifact) setSelectedArtifact(diffArtifact);
  }, [waitingApproval, diffArtifact, selectedArtifact]);

  useEffect(() => {
    if (reportDone && reportArtifact && !selectedArtifact) setSelectedArtifact(reportArtifact);
  }, [reportDone, reportArtifact, selectedArtifact]);

  if (!run) return (
    <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "64px 0", color: "var(--text-muted)" }}>
      <div className="spinner" /> Loading run…
    </div>
  );

  const priorityKinds = ["proposal_diff", "report", "post_checks_log", "baseline_log", "signals_text", "plan", "context", "smoke_log"];
  const sortedArtifacts = [
    ...priorityKinds.map((k) => artifacts.find((a) => a.kind === k)).filter(Boolean),
    ...artifacts.filter((a) => !priorityKinds.includes(a.kind)),
  ];

  function artifactLabel(a) {
    const labels = {
      proposal_diff: "📋 Diff",
      report: "📄 Report",
      baseline_log: "⚠️ Baseline",
      post_checks_log: "✅ Post-checks",
      smoke_log: "💨 Smoke",
      signals_text: "🔍 Signals",
      context: "📚 Context",
      plan: "📝 Plan",
      apply_result: "✓ Apply",
      invalid_patch: "⛔ Invalid",
      next_actions: "💡 Actions",
    };
    return labels[a.kind] || a.kind?.replace(/_/g, " ");
  }

  const runningStep = steps.find((s) => s.status === "running");

  return (
    <div>
      {/* Header */}
      <div className="flex items-center justify-between mb-16" style={{ flexWrap: "wrap", gap: 12 }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
            <Link href="/" className="text-muted text-sm" style={{ flexShrink: 0 }}>← Dashboard</Link>
            <span className="text-muted">/</span>
            <h1 style={{ fontSize: 18, fontWeight: 800, letterSpacing: "-0.4px" }} className="truncate">{run.title}</h1>
            <StatusPill status={run.status} />
          </div>
          <div className="run-meta mt-8">
            <span>🗂 <span className="workspace-badge">{run.workspace}</span></span>
            <span>🆔 <code style={{ fontSize: 11 }}>{String(id).slice(0, 8)}…</code></span>
            {run.created_at && <span>🕐 {new Date(run.created_at).toLocaleString()}</span>}
          </div>
        </div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          {canStart && <button className="btn btn-primary btn-sm" onClick={start} disabled={busy}>⚡ Start</button>}
          {isActive && <button className="btn btn-ghost btn-sm" onClick={cancelRun} disabled={busy}>✕ Cancel</button>}
          {(isFailed || isCompleted) && <button className="btn btn-ghost btn-sm" onClick={retry} disabled={busy}>↺ Retry</button>}
          {canRegenerate && <button className="btn btn-outline btn-sm" onClick={regenerate} disabled={busy}>🔄 Regen patch</button>}
          <Link href={`${API_BASE}/runs/${id}/download`} className="btn btn-ghost btn-sm">⬇ Download</Link>
          <button className="btn btn-danger btn-sm" onClick={deleteRun} disabled={busy}>🗑 Delete</button>
        </div>
      </div>

      {/* Messages */}
      {err && <div className="alert error mb-12">{err}</div>}
      {actionMsg && <div className="alert success mb-12">{actionMsg}</div>}

      {/* Progress bar */}
      <div className="mb-16">
        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, color: "var(--text-muted)", marginBottom: 6 }}>
          <span>{runningStep ? `Running: ${runningStep.name}` : isCompleted ? "All steps complete" : isFailed ? "Pipeline failed" : "Ready"}</span>
          <span className="text-mono">{doneCount}/{TOTAL_STEPS} steps • {progress}%</span>
        </div>
        <div className="progress-bar">
          <div className="progress-fill" style={{ width: `${progress}%` }} />
        </div>
      </div>

      {/* Approval box */}
      {waitingApproval && (
        <div className="approval-box mb-16 animate-in">
          <div className="approval-title">
            ⏸ Review the proposed patch
          </div>
          <p style={{ fontSize: 13, color: "var(--text-secondary)", marginBottom: 14 }}>
            The AI has proposed a patch. Review the diff below, then approve or reject it.
          </p>
          <div style={{ display: "flex", gap: 8 }}>
            <button className="btn btn-success" onClick={approve} disabled={busy}>✓ Approve & Apply</button>
            <button className="btn btn-danger" onClick={reject} disabled={busy}>✕ Reject</button>
            <button className="btn btn-ghost btn-sm" onClick={regenerate} disabled={busy}>🔄 Regenerate</button>
          </div>
        </div>
      )}

      {/* Signals */}
      {signals.length > 0 && (
        <div className="mb-16">
          <div className="text-xs text-muted" style={{ marginBottom: 6, fontWeight: 600, letterSpacing: "0.4px", textTransform: "uppercase" }}>Detected Issues</div>
          <SignalChips signals={signals} />
        </div>
      )}

      {/* 3-column layout */}
      <div style={{ display: "grid", gridTemplateColumns: "260px 1fr", gap: 20, alignItems: "start" }}>

        {/* Steps panel */}
        <div className="card" style={{ padding: "16px" }}>
          <div className="section-header">
            <span className="section-title">Pipeline Steps</span>
          </div>
          <div className="step-list pipeline-track">
            {steps.map((s, idx) => (
              <div key={s.id} className={`step-item${s.status === "running" ? " active" : s.status === "failed" ? " failed" : ""}`}>
                <span className="step-number">{idx + 1}</span>
                <StepIcon status={s.status} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div className="step-name">{s.name}</div>
                  {s.summary && <div className="step-summary">{s.summary}</div>}
                  {s.error && <div className="step-error">⚠ {s.error}</div>}
                </div>
              </div>
            ))}
            {steps.length === 0 && (
              <div className="empty-state" style={{ padding: "24px 0" }}>
                <div style={{ fontSize: 11, color: "var(--text-muted)" }}>Start the run to see steps</div>
              </div>
            )}
          </div>
        </div>

        {/* Artifacts viewer */}
        <div className="card" style={{ minWidth: 0 }}>
          <div className="section-header">
            <span className="section-title">Artifacts</span>
            {selectedArtifact && (
              <span className="text-muted text-xs text-mono">{selectedArtifact.kind}</span>
            )}
          </div>

          {sortedArtifacts.length > 0 ? (
            <>
              <div className="artifact-tabs">
                {sortedArtifacts.map((a) => (
                  <button key={a.id} className={`artifact-tab${selectedArtifact?.id === a.id ? " active" : ""}`}
                    onClick={() => setSelectedArtifact(a)}>
                    {artifactLabel(a)}
                  </button>
                ))}
              </div>

              <div className="code-viewer">
                {artifactLoading ? (
                  <div style={{ display: "flex", alignItems: "center", gap: 10, padding: 20, color: "var(--text-muted)" }}>
                    <div className="spinner" /> Loading…
                  </div>
                ) : selectedArtifact?.kind === "proposal_diff" ? (
                  <DiffView text={artifactText} />
                ) : (
                  <pre style={{ padding: 16, color: "#9aa8bc", whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
                    {artifactText || "(Select an artifact to view its contents)"}
                  </pre>
                )}
              </div>
            </>
          ) : (
            <div className="empty-state">
              <div className="empty-icon">📂</div>
              <div className="text-muted text-sm">No artifacts yet — run the pipeline to generate outputs</div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
