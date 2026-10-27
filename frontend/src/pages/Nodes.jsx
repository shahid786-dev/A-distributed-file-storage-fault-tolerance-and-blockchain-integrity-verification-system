import { useState } from "react";
import { Button, Empty, ErrorNote, HashChip, Note, Pill, Section, Spinner, fmtBytes, fmtTime, nodeLabel, useAction } from "../components/ui.jsx";
import { api } from "../services/api.js";

function NodeFiles({ nodeId }) {
  const act = useAction();
  const [open, setOpen] = useState(false);
  const toggle = () => {
    if (!open) act.run(() => api.nodeFiles(nodeId));
    setOpen(!open);
  };
  return (
    <div>
      <button className="btn btn--ghost btn--small" onClick={toggle} aria-expanded={open}>
        {open ? "Hide stored files" : "Inspect stored file hashes"}
      </button>
      {open && (
        <>
          {act.busy && <Spinner />}
          <ErrorNote error={act.error} />
          {act.result && (act.result.files.length === 0 ? <Empty>This node stores no files.</Empty> : (
            <ul className="node-files">
              {act.result.files.map((f) => (
                <li key={f.file_id}>
                  <span>{f.name} <span className="muted">({fmtBytes(f.size)})</span></span>
                  <HashChip hash={f.sha256} length={8} />
                  <Pill value={f.hash_match ? "match" : "mismatch"} label={f.hash_match ? "matches trusted" : "differs"} />
                </li>
              ))}
            </ul>
          ))}
        </>
      )}
    </div>
  );
}

export default function Nodes({ nodes, error, refresh, isAdmin }) {
  const act = useAction();
  const [msg, setMsg] = useState(null);
  if (!nodes) return error ? <ErrorNote error={error} /> : <Spinner />;

  const fail = async (id) => {
    if (!window.confirm(`TEST: make ${nodeLabel(id)} refuse all requests (simulated failure)?`)) return;
    const r = await act.run(() => api.failNode(id));
    if (r) setMsg(`${nodeLabel(id)} is now in simulated failure mode and answers every request with HTTP 503.`);
    refresh();
  };
  const restart = async (id) => {
    const r = await act.run(() => api.restartNode(id));
    if (r) setMsg(`${nodeLabel(id)} is back in service; its ledger was synchronised (${r.node.ledger_height} blocks).`);
    refresh();
  };

  return (
    <>
      <Note>
        <strong>Two kinds of failure.</strong> “Simulate failure” keeps the node process running but makes it refuse every
        request (HTTP 503). A <em>real</em> failure is stopping the process or container from a terminal —{" "}
        <code>docker compose stop node2</code> or <code>python run_local.py stop-node node2</code>. The health checks below
        detect both the same way.
      </Note>
      {msg && <Note tone="ok">{msg}</Note>}
      <ErrorNote error={act.error} />
      <div className="node-grid">
        {nodes.map((n) => (
          <article key={n.node_id} className={`node-card${n.online ? "" : " node-card--down"}`}>
            <header>
              <h2>{nodeLabel(n.node_id)}</h2>
              <Pill value={n.online ? "online" : "offline"} />
              {n.malicious_simulation && <Pill value="malicious" label="malicious test mode" />}
            </header>
            <dl className="facts facts--stack">
              <div><dt>Endpoint</dt><dd><code>{n.url}</code></dd></div>
              <div><dt>Latest health check</dt><dd>{n.online ? "passed" : `failed: ${n.last_error}`} <span className="muted">({fmtTime(n.last_checked)})</span></dd></div>
              <div><dt>Stored files</dt><dd>{n.file_count ?? "–"}</dd></div>
              <div><dt>Ledger height</dt><dd>{n.ledger_height ?? "–"}</dd></div>
              <div><dt>Ledger head</dt><dd><HashChip hash={n.ledger_head_hash} length={12} /></dd></div>
              <div><dt>Integrity</dt><dd><Pill value={n.corrupted_replicas ? "mismatch" : "match"} label={n.corrupted_replicas ? `${n.corrupted_replicas} corrupted replica(s)` : "no problems found"} /></dd></div>
              <div><dt>Health checks</dt><dd>{n.health_checks_ok} passed, {n.health_checks_failed} failed</dd></div>
            </dl>
            {isAdmin && <div className="btn-row">
              {n.online ? (
                <Button small variant="danger" busy={act.busy} onClick={() => fail(n.node_id)}>Simulate node failure</Button>
              ) : (
                <Button small busy={act.busy} onClick={() => restart(n.node_id)}>Restart node</Button>
              )}
            </div>}
            {n.online && <NodeFiles nodeId={n.node_id} />}
          </article>
        ))}
      </div>
    </>
  );
}
