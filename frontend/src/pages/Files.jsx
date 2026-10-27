import { useRef, useState } from "react";
import { IntegrityTable, SummaryLine } from "../components/Results.jsx";
import {
  Button, Empty, ErrorNote, HashChip, Note, Pill, Section, Spinner, fmtBytes, fmtTime, nodeLabel, useAction, usePoll,
} from "../components/ui.jsx";
import { api } from "../services/api.js";

function UploadPanel({ onDone }) {
  const input = useRef(null);
  const [file, setFile] = useState(null);
  const up = useAction();

  async function submit(e) {
    e.preventDefault();
    if (!file) return;
    const r = await up.run(() => api.upload(file));
    if (r) {
      onDone(r);
      setFile(null);
      if (input.current) input.current.value = "";
    }
  }
  const r = up.result;
  return (
    <Section title="Upload a file" id="upload">
      <form className="upload" onSubmit={submit}>
        <label className="upload__drop">
          <input ref={input} type="file" onChange={(e) => setFile(e.target.files[0] || null)} aria-label="Choose a file to upload" />
          <span>{file ? `${file.name} (${fmtBytes(file.size)})` : "Choose a file — txt, md, csv, json, pdf, images, Office files or zip, up to 10 MB"}</span>
        </label>
        <Button type="submit" busy={up.busy} disabled={!file}>Upload and replicate</Button>
      </form>
      <ErrorNote error={up.error} />
      {up.error?.body?.replicas && <ReplicaResult replicas={up.error.body.replicas} />}
      {r && (
        <div className="result">
          <Note tone={r.fully_replicated ? "ok" : "warn"}>
            <strong>{r.name}</strong> stored on {r.healthy_replicas} of 5 nodes
            {r.fully_replicated ? "." : ` — ${r.failed_replicas} node(s) did not receive a verified copy.`} Recorded in
            ledger block #{r.ledger_block}. Trusted SHA-256 <HashChip hash={r.sha256} length={16} />
          </Note>
          <ReplicaResult replicas={r.replicas} />
          <p className="muted">
            Timing: hash {r.timing_ms.hash} ms · replication {r.timing_ms.replication} ms · ledger vote and commit{" "}
            {r.timing_ms.ledger_commit} ms · total {r.timing_ms.total} ms
          </p>
        </div>
      )}
    </Section>
  );
}

function ReplicaResult({ replicas }) {
  return (
    <ul className="replica-strip">
      {replicas.map((x) => (
        <li key={x.node_id} className={x.hash_match ? "ok" : "bad"}>
          <strong>{nodeLabel(x.node_id)}</strong>
          <span>{x.hash_match ? "stored, hash verified" : x.error || "not stored"}</span>
        </li>
      ))}
    </ul>
  );
}

function VersionPanel({ file, onDone }) {
  const input = useRef(null);
  const [nextFile, setNextFile] = useState(null);
  const action = useAction();

  async function submit(event) {
    event.preventDefault();
    if (!nextFile) return;
    const result = await action.run(() => api.uploadVersion(file.file_id, file.version_number, nextFile));
    if (result) {
      onDone(result);
      setNextFile(null);
      if (input.current) input.current.value = "";
    }
  }

  return (
    <Section title={`Create version ${file.version_number + 1}`} id="new-version">
      <p className="muted">Version {file.version_number} remains immutable. A stale parent is rejected if another version commits first.</p>
      <form className="upload" onSubmit={submit}>
        <label className="upload__drop">
          <input ref={input} type="file" onChange={(event) => setNextFile(event.target.files[0] || null)}
            aria-label="Choose the next document version" />
          <span>{nextFile ? `${nextFile.name} (${fmtBytes(nextFile.size)})` : "Choose replacement document contents"}</span>
        </label>
        <Button type="submit" busy={action.busy} disabled={!nextFile}>Upload new version</Button>
      </form>
      <ErrorNote error={action.error} />
      {action.result && <Note tone="ok">Created immutable version {action.result.version_number}; ledger block #{action.result.ledger_block}.</Note>}
    </Section>
  );
}

function FileDetail({ file, onChanged, onSelect, user }) {
  const live = usePoll(() => api.replicas(file.file_id), 0, [file.file_id]);
  const shares = usePoll(
    () => file.access === "owner" && user.role === "admin" ? api.shares(file.file_id) : Promise.resolve([]),
    0, [file.file_id, file.access, user.role],
  );
  const act = useAction();
  const shareAction = useAction();
  const [msg, setMsg] = useState(null);
  const [shareOrganization, setShareOrganization] = useState(
    user.organization === "manufacturer" ? "logistics" : "manufacturer",
  );
  const canManage = file.access === "owner" && user.role === "admin";
  const canVersion = file.access === "owner" && Boolean(file.is_latest);
  const report = act.result && act.result.replicas_after
    ? { ...act.result, replicas: act.result.replicas_after, summary: act.result.summary_after }
    : act.result || live.data;

  const verify = async () => {
    setMsg(null);
    const r = await act.run(() => api.verify(file.file_id));
    if (r) { setMsg({ tone: r.summary.mismatched ? "warn" : "ok", text: `Integrity check recorded in ledger (${r.ledger.outcome}, block #${r.ledger.block ?? "–"}). Took ${r.duration_ms} ms.` }); onChanged(); }
  };
  const recover = async () => {
    setMsg(null);
    const r = await act.run(() => api.recover(file.file_id));
    if (r) {
      setMsg({
        tone: "ok",
        text: `Verified copy obtained from ${nodeLabel(r.source_node)} (hash matches the trusted hash). ` +
          (r.repaired_nodes.length ? `Repaired: ${r.repaired_nodes.map(nodeLabel).join(", ")}. ` : "No copies needed repair. ") +
          (r.unavailable_nodes.length ? `Still offline: ${r.unavailable_nodes.map(nodeLabel).join(", ")}.` : ""),
      });
      onChanged();
    }
  };
  const grantShare = async (event) => {
    event.preventDefault();
    const result = await shareAction.run(() => api.share(file.file_id, shareOrganization));
    if (result) shares.reload();
  };
  const revokeShare = async (organization) => {
    const result = await shareAction.run(() => api.revokeShare(file.file_id, organization));
    if (result) shares.reload();
  };
  const download = async () => {
    setMsg(null);
    const r = await act.run(() => api.download(file.file_id, file.name));
    if (r) setMsg({ tone: "ok", text: `Downloaded ${fmtBytes(r.size)} from ${nodeLabel(r.sourceNode)}; SHA-256 verified by the coordinator before sending.${r.skipped ? ` Skipped: ${r.skipped}.` : ""}` });
  };

  return (
    <Section title={file.name} id="file-detail"
      aside={
        <div className="btn-row">
          <Button small onClick={verify} busy={act.busy}>Verify integrity</Button>
          <Button small variant="secondary" onClick={download} busy={act.busy}>Download verified copy</Button>
          {canManage && <Button small variant="secondary" onClick={recover} busy={act.busy}>Recover file</Button>}
        </div>
      }>
      <dl className="facts">
        <div><dt>File id</dt><dd><code>{file.file_id}</code></dd></div>
        <div><dt>Document version</dt><dd>{file.version_number} {file.is_latest ? "· latest" : ""}</dd></div>
        <div><dt>Document id</dt><dd><code>{file.document_id}</code></dd></div>
        {file.previous_file_id && <div><dt>Parent version</dt><dd><code>{file.previous_file_id}</code></dd></div>}
        <div><dt>Size</dt><dd>{fmtBytes(file.size)}</dd></div>
        <div><dt>Uploaded</dt><dd>{fmtTime(file.uploaded_at)}</dd></div>
        <div><dt>Owner</dt><dd>{file.owner_org_id}{file.access === "shared" ? " · shared with you" : ""}</dd></div>
        <div><dt>Ledger block</dt><dd>#{file.ledger_block}</dd></div>
        <div className="facts__wide"><dt>Trusted SHA-256</dt><dd><code className="break">{file.sha256}</code></dd></div>
      </dl>
      {canVersion && <VersionPanel file={file} onDone={(result) => { onChanged(); onSelect(result.file_id); }} />}
      {msg && <Note tone={msg.tone}>{msg.text}</Note>}
      <ErrorNote error={act.error || live.error} />
      {act.error?.body?.attempts && (
        <ul className="replica-strip">
          {act.error.body.attempts.map((a) => <li key={a.node_id} className="bad"><strong>{nodeLabel(a.node_id)}</strong><span>{a.result}</span></li>)}
        </ul>
      )}
      {canManage && (
        <Section title="Organization sharing" id="file-sharing">
          <form className="share-form" onSubmit={grantShare}>
            <label>
              Grant read access to
              <select value={shareOrganization} onChange={(event) => setShareOrganization(event.target.value)}>
                {[
                  ["manufacturer", "Northstar Manufacturing"],
                  ["logistics", "Wayline Logistics"],
                  ["inspection", "Clearview Quality Inspection"],
                  ["distributor", "Harborlight Distribution"],
                ].filter(([id]) => id !== user.organization).map(([id, name]) => (
                  <option key={id} value={id}>{name}</option>
                ))}
              </select>
            </label>
            <Button type="submit" busy={shareAction.busy}>Share read-only</Button>
          </form>
          <ErrorNote error={shareAction.error || shares.error} onRetry={shares.reload} />
          {!shares.data ? <Spinner /> : shares.data.length === 0 ? <Empty>Not shared with another organization.</Empty> : (
            <ul className="share-list">
              {shares.data.map((entry) => (
                <li key={entry.organization}>
                  <span>{entry.name} <span className="muted">({entry.permission})</span></span>
                  <Button small variant="danger" busy={shareAction.busy}
                    onClick={() => revokeShare(entry.organization)}>Revoke</Button>
                </li>
              ))}
            </ul>
          )}
        </Section>
      )}
      {!report ? <Spinner label="Checking replicas" /> : (
        <>
          <SummaryLine summary={report.summary} />
          <IntegrityTable report={report} />
        </>
      )}
      <button className="btn btn--ghost btn--small" onClick={() => { act.setResult(null); live.reload(); }}>Re-check replicas now</button>
    </Section>
  );
}

export default function Files({ user }) {
  const list = usePoll(api.files, 5000);
  const [selected, setSelected] = useState(null);
  const files = list.data || [];
  const current = files.find((f) => f.file_id === selected);

  return (
    <>
      <UploadPanel onDone={(r) => { list.reload(); setSelected(r.file_id); }} />
      <Section title="Stored files" id="files">
        <ErrorNote error={list.error} onRetry={list.reload} />
        {list.loading && !list.data ? <Spinner /> : files.length === 0 ? (
          <Empty>No files yet. Upload one above, or try sample_files/sample_document.txt from the project folder.</Empty>
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th scope="col">Name</th><th scope="col">Size</th><th scope="col">Uploaded</th>
                  <th scope="col">Version</th>
                  <th scope="col">Trusted hash</th><th scope="col">Replicas (last check)</th><th scope="col"><span className="sr-only">Open</span></th>
                </tr>
              </thead>
              <tbody>
                {files.map((f) => {
                  const c = f.replica_counts;
                  return (
                    <tr key={f.file_id} className={f.file_id === selected ? "row--selected" : ""}>
                      <th scope="row">{f.name}</th>
                      <td>{fmtBytes(f.size)}</td>
                      <td>{fmtTime(f.uploaded_at)}</td>
                      <td>v{f.version_number}{f.is_latest ? " · latest" : ""}</td>
                      <td><HashChip hash={f.sha256} /></td>
                      <td className="counts">
                        <Pill value="match" label={`${c.match} match`} />
                        {c.mismatch > 0 && <Pill value="mismatch" label={`${c.mismatch} corrupted`} />}
                        {c.missing + c.unavailable > 0 && <Pill value="missing" label={`${c.missing + c.unavailable} missing/offline`} />}
                      </td>
                      <td><button className="btn btn--ghost btn--small" onClick={() => setSelected(f.file_id)}>Details</button></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Section>
      {current && <FileDetail key={current.file_id} file={current} onChanged={list.reload}
        onSelect={setSelected} user={user} />}
    </>
  );
}
