"use client";

import { useEffect, useState, useCallback } from "react";
import { apiGet, apiPost, apiPostForm } from "./lib/api";
import Link from "next/link";

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

const PRESETS = [
  {
    id: "repair",
    emoji: "🔧",
    name: "Fix failing tests",
    desc: "AI finds bugs, proposes a patch, verifies the fix",
    ticket_text:
      "Fix all failing tests.\n\nAnalyze the test output carefully. Identify the root cause of each failure, then apply a minimal patch that makes ALL tests pass. Do not change the tests themselves — only fix the implementation.",
    title: "Fix failing tests",
  },
  {
    id: "feature",
    emoji: "✨",
    name: "Add a feature",
    desc: "Implement a new feature with tests",
    ticket_text:
      "Add a GET /health endpoint that returns {\"status\": \"ok\", \"version\": \"1.0\"}.\nEnsure the tests pass after adding the endpoint.",
    title: "Add /health endpoint",
  },
  {
    id: "refactor",
    emoji: "♻️",
    name: "Refactor code",
    desc: "Improve code quality while keeping tests green",
    ticket_text:
      "Refactor the implementation to improve code quality:\n- Extract magic numbers into named constants\n- Add docstrings to all public functions\n- Ensure all existing tests still pass after refactoring",
    title: "Refactor: improve code quality",
  },
  {
    id: "perf",
    emoji: "⚡",
    name: "Optimize performance",
    desc: "Find and fix performance bottlenecks",
    ticket_text:
      "Analyze the code for performance issues. Look for:\n- Unnecessary recomputation\n- Inefficient loops or data structures\n- Missing memoization or caching\n\nApply improvements and ensure all tests still pass.",
    title: "Optimize performance",
  },
  {
    id: "custom",
    emoji: "✏️",
    name: "Custom request",
    desc: "Write your own task description",
    ticket_text: "",
    title: "",
  },
  {
    id: "swebench",
    emoji: "🏋️",
    name: "SWE-bench eval",
    desc: "Evaluate AI on real GitHub issues",
    ticket_text: `#spec2ship: swebench_eval
prompt_dataset=princeton-nlp/SWE-bench_Lite_bm25_13K
dataset_name=princeton-nlp/SWE-bench_Lite
split=test
limit=2
model=qwen2.5-coder:7b
timeout=600
max_workers=1`,
    title: "SWE-bench evaluation (2 issues)",
  },
];

export default function Home() {
  const [runs, setRuns] = useState([]);
  const [workspaces, setWorkspaces] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [uploadBusy, setUploadBusy] = useState(false);
  const [uploadMsg, setUploadMsg] = useState("");
  const [uploadFile, setUploadFile] = useState(null);
  const [uploadName, setUploadName] = useState("");
  const [dragging, setDragging] = useState(false);
  const [selectedPreset, setSelectedPreset] = useState("repair");
  const [form, setForm] = useState({
    title: PRESETS[0].title,
    ticket_text: PRESETS[0].ticket_text,
    workspace: "sample_workspace",
  });
  const [stats, setStats] = useState({ total: 0, completed: 0, failed: 0 });

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const data = await apiGet("/runs/");
      const list = Array.isArray(data) ? data : [];
      setRuns(list.slice(0, 30));
      setStats({
        total: list.length,
        completed: list.filter((r) => r.status === "completed").length,
        failed: list.filter((r) => r.status === "failed" || r.status === "canceled").length,
      });
    } catch (e) {
      setErr(e?.message || String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  const refreshWorkspaces = useCallback(async () => {
    try {
      const data = await apiGet("/workspaces/");
      const list = Array.isArray(data) ? data : [];
      setWorkspaces(list);
      const names = new Set(list.map((w) => w.name));
      setForm((f) => ({ ...f, workspace: names.has(f.workspace) ? f.workspace : (list[0]?.name || "sample_workspace") }));
    } catch {}
  }, []);

  useEffect(() => {
    refresh();
    refreshWorkspaces();
    const t = setInterval(refresh, 4000);
    return () => clearInterval(t);
  }, [refresh, refreshWorkspaces]);

  function selectPreset(id) {
    const p = PRESETS.find((p) => p.id === id);
    if (!p) return;
    setSelectedPreset(id);
    setForm((f) => ({ ...f, title: p.title || f.title, ticket_text: p.ticket_text }));
  }

  async function onCreate(e) {
    e.preventDefault();
    if (!form.ticket_text.trim()) { setErr("Please describe what you want done."); return; }
    setBusy(true); setErr("");
    try {
      const r = await apiPost("/runs/", form);
      await refresh();
      if (r?.id) window.location.href = `/runs/${r.id}`;
    } catch (e) {
      setErr(e?.message || String(e));
    } finally { setBusy(false); }
  }

  async function resetWorkspace() {
    setBusy(true); setErr("");
    try { await apiPost("/workspaces/sample/reset"); await refreshWorkspaces(); }
    catch (e) { setErr(e?.message || String(e)); }
    finally { setBusy(false); }
  }

  async function handleUpload(file) {
    if (!file || !file.name.endsWith(".zip")) { setUploadMsg("Please select a .zip file."); return; }
    setUploadBusy(true); setUploadMsg("Uploading and extracting...");
    try {
      const fd = new FormData();
      fd.append("file", file);
      if (uploadName.trim()) fd.append("name", uploadName.trim());
      const res = await apiPostForm("/workspaces/upload", fd);
      if (res?.ok) {
        setUploadMsg(`✓ Imported: ${res.name} (${res.file_count} files)`);
        setUploadFile(null); setUploadName("");
        await refreshWorkspaces();
        if (res?.name) setForm((f) => ({ ...f, workspace: res.name }));
      }
    } catch (e) {
      setUploadMsg(`Upload failed: ${e?.message || String(e)}`);
    } finally { setUploadBusy(false); }
  }

  function onDrop(e) {
    e.preventDefault(); setDragging(false);
    const file = e.dataTransfer.files?.[0];
    if (file) { setUploadFile(file); handleUpload(file); }
  }

  const recent = runs.slice(0, 8);

  return (
    <div className="split" style={{ gap: 28 }}>

      {/* ── Left: runs + stats ── */}
      <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>

        {/* Stats row */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12 }}>
          {[
            { label: "Total Runs", value: stats.total, color: "var(--text)" },
            { label: "Completed", value: stats.completed, color: "var(--green)" },
            { label: "Failed", value: stats.failed, color: stats.failed > 0 ? "var(--red)" : "var(--text-muted)" },
          ].map((s) => (
            <div key={s.label} className="card" style={{ padding: "14px 18px" }}>
              <div style={{ fontSize: 26, fontWeight: 800, color: s.color, fontFamily: "var(--mono)" }}>{s.value}</div>
              <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 2, fontWeight: 600, letterSpacing: "0.4px", textTransform: "uppercase" }}>{s.label}</div>
            </div>
          ))}
        </div>

        {/* Recent runs */}
        <div className="card">
          <div className="flex items-center justify-between mb-16">
            <div>
              <div className="card-title">Recent Runs</div>
              <div className="card-desc mt-8">Auto-refreshes every 4s</div>
            </div>
            <div style={{ display: "flex", gap: 8 }}>
              {loading && <div className="spinner" />}
              <Link href="/runs" className="btn btn-ghost btn-sm">View all →</Link>
            </div>
          </div>

          {err && <div className="alert error mb-12">{err}</div>}

          {recent.length === 0 ? (
            <div className="empty-state">
              <div className="empty-icon">🚀</div>
              <div style={{ fontSize: 13, color: "var(--text-muted)" }}>No runs yet — create your first run →</div>
            </div>
          ) : (
            <table className="data-table">
              <thead><tr>
                <th>Title</th><th>Workspace</th><th>Status</th><th>Created</th><th></th>
              </tr></thead>
              <tbody>
                {recent.map((r) => (
                  <tr key={r.id}>
                    <td style={{ maxWidth: 200 }} className="truncate" title={r.title}>{r.title}</td>
                    <td><span className="workspace-badge">{r.workspace || "—"}</span></td>
                    <td><StatusPill status={r.status} /></td>
                    <td className="text-muted text-xs text-mono">
                      {r.created_at ? new Date(r.created_at).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : "—"}
                    </td>
                    <td>
                      <Link className="btn btn-ghost btn-xs" href={`/runs/${r.id}`}>Open →</Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* How it works */}
        <div className="card" style={{ padding: "18px 22px" }}>
          <div className="card-title mb-12">How it works</div>
          {[
            ["📦", "Upload", "Drop a .zip of your project"],
            ["📝", "Describe", "Tell the AI what to fix or build"],
            ["🤖", "AI Pipeline", "Spec2Ship detects issues, proposes a patch, applies it"],
            ["✅", "Verify", "Post-checks confirm everything passes"],
            ["🔁", "Auto-repair", "If tests still fail, AI retries automatically"],
          ].map(([icon, title, desc]) => (
            <div key={title} style={{ display: "flex", gap: 12, alignItems: "flex-start", marginBottom: 10 }}>
              <span style={{ fontSize: 16 }}>{icon}</span>
              <div>
                <span style={{ fontSize: 13, fontWeight: 700 }}>{title}</span>
                <span style={{ fontSize: 12, color: "var(--text-muted)", marginLeft: 6 }}>{desc}</span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* ── Right: upload + create ── */}
      <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>

        {/* Upload workspace */}
        <div className="card">
          <div className="card-title mb-8">① Upload your codebase</div>
          <div className="card-desc mb-16">
            Zip your project folder and drop it here. <code>node_modules</code>, <code>.git</code> and build artifacts are skipped automatically.
            Works with Python, Node.js, Go, Rust, Java, Ruby, and more.
          </div>

          <div
            className={`upload-zone${dragging ? " dragging" : ""}`}
            onClick={() => document.getElementById("zip-input").click()}
            onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
          >
            <input id="zip-input" type="file" accept=".zip"
              onChange={(e) => { const f = e.target.files?.[0]; if (f) { setUploadFile(f); handleUpload(f); } }} />
            <div className="upload-icon">{uploadBusy ? "⏳" : "📦"}</div>
            <div style={{ fontSize: 13, color: "var(--text-secondary)", fontWeight: 600 }}>
              {uploadBusy ? "Processing..." : "Click or drag a .zip file here"}
            </div>
            {uploadFile && !uploadBusy && (
              <div className="text-muted text-xs mt-8 text-mono">{uploadFile.name}</div>
            )}
          </div>

          {uploadMsg && (
            <div className={`alert ${uploadMsg.startsWith("✓") ? "success" : uploadMsg.startsWith("Upload failed") ? "error" : "info"} mt-12`}>
              {uploadMsg}
            </div>
          )}

          <div style={{ display: "flex", gap: 10, marginTop: 14, alignItems: "center" }}>
            <div style={{ flex: 1 }}>
              <div className="field">
                <label className="label">Workspace name (optional)</label>
                <input className="input" placeholder="my-project" value={uploadName} onChange={(e) => setUploadName(e.target.value)} />
              </div>
            </div>
          </div>

          <div style={{ display: "flex", gap: 10, marginTop: 12, alignItems: "center" }}>
            <select className="select" value={form.workspace} onChange={(e) => setForm({ ...form, workspace: e.target.value })} style={{ flex: 1 }}>
              {(workspaces.length ? workspaces : [{ name: "sample_workspace" }]).map((w) => (
                <option key={w.name} value={w.name}>{w.name}</option>
              ))}
            </select>
            <button className="btn btn-ghost btn-sm" onClick={resetWorkspace} disabled={busy} style={{ whiteSpace: "nowrap" }}>
              ↺ Reset sample
            </button>
          </div>
        </div>

        {/* Create run */}
        <div className="card">
          <div className="card-title mb-8">② Describe the task</div>
          <div className="card-desc mb-16">Choose a template or write your own request. Be specific for best results.</div>

          <div className="preset-grid mb-16">
            {PRESETS.map((p) => (
              <button key={p.id} className={`preset-card${selectedPreset === p.id ? " selected" : ""}`} onClick={() => selectPreset(p.id)}>
                <div className="preset-emoji">{p.emoji}</div>
                <div className="preset-name">{p.name}</div>
                <div className="preset-desc">{p.desc}</div>
              </button>
            ))}
          </div>

          <form onSubmit={onCreate} style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            <div className="field">
              <label className="label">Run title</label>
              <input className="input" placeholder="Brief description" value={form.title}
                onChange={(e) => setForm({ ...form, title: e.target.value })} required />
            </div>

            <div className="field">
              <label className="label">Ticket / Request</label>
              <textarea className="textarea mono" rows={8}
                placeholder="Describe what needs to be done. Be specific — mention which tests are failing, what feature to add, or what behavior to fix."
                value={form.ticket_text} onChange={(e) => setForm({ ...form, ticket_text: e.target.value })} />
            </div>

            {err && <div className="alert error">{err}</div>}

            <button className="btn btn-primary" type="submit" disabled={busy} style={{ width: "100%", justifyContent: "center", padding: "12px" }}>
              {busy ? <><div className="spinner" /> Creating run…</> : "⚡ Create & Start Run →"}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
