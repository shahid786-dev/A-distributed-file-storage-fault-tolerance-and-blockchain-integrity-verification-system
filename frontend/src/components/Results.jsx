// Tables that show real results returned by the backend.
import { Fragment, useState } from "react";
import { HashChip, Pill, fmtTime, nodeLabel } from "./ui.jsx";

// Per-node integrity table (verify / replicas / recover responses)
export function IntegrityTable({ report }) {
  if (!report) return null;
  const rows = report.replicas || report.replicas_after || [];
  return (
    <div className="table-wrap">
      <table className="table">
        <caption>
          Each copy is downloaded and hashed by the coordinator, then compared with the trusted hash{" "}
          <HashChip hash={report.trusted_hash} length={12} />
        </caption>
        <thead>
          <tr>
            <th scope="col">Node</th>
            <th scope="col">Status</th>
            <th scope="col">Hash match</th>
            <th scope="col">Hash calculated by coordinator</th>
            <th scope="col">Hash claimed by node</th>
            <th scope="col">Action</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.node_id} className={r.status === "mismatch" ? "row--bad" : ""}>
              <th scope="row">{nodeLabel(r.node_id)}</th>
              <td>
                <Pill value={r.online === false ? "offline" : "online"} />
              </td>
              <td>
                <Pill
                  value={r.status}
                  label={r.status === "match" ? "Yes" : r.status === "mismatch" ? "No" : r.status}
                />
              </td>
              <td>{r.computed_hash ? <HashChip hash={r.computed_hash} /> : "–"}</td>
              <td>
                {r.reported_hash ? <HashChip hash={r.reported_hash} /> : "–"}
                {r.node_reported_falsely && <span className="tag tag--bad">false claim</span>}
              </td>
              <td>{r.action || r.error || "–"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function SummaryLine({ summary }) {
  if (!summary) return null;
  return (
    <p className="summary-line">
      <span>Expected {summary.expected}</span>
      <span className="ok">{summary.healthy} matching</span>
      <span className={summary.mismatched ? "bad" : ""}>{summary.mismatched} corrupted</span>
      <span className={summary.missing ? "warn" : ""}>{summary.missing} missing</span>
      <span className={summary.unavailable ? "warn" : ""}>{summary.unavailable} unavailable</span>
    </p>
  );
}

// One consensus round: proposer, votes, outcome and before/after heads
export function ProposalView({ proposal, compact }) {
  const [showBlock, setShowBlock] = useState(false);
  if (!proposal) return null;
  const nodes = Object.keys(proposal.heads_before || {});
  return (
    <div className={`proposal proposal--${proposal.outcome}`}>
      <div className="proposal__head">
        <Pill value={proposal.outcome} label={proposal.outcome === "committed" ? "Committed" : "Rejected"} />
        <span>
          Block #{proposal.block?.index} proposed by <strong>{proposal.proposer}</strong> ·{" "}
          <strong>
            {proposal.accept_count} accept / {proposal.reject_count} reject
          </strong>{" "}
          (quorum 3 of 5)
        </span>
        <span className="muted">{fmtTime(proposal.created_at)}</span>
      </div>
      <p className="proposal__reason">{proposal.reason}</p>
      <div className="table-wrap">
        <table className="table table--tight">
          <thead>
            <tr>
              <th scope="col">Voter</th>
              <th scope="col">Vote</th>
              <th scope="col">Reason given by the node</th>
              {!compact && <th scope="col">Signature</th>}
            </tr>
          </thead>
          <tbody>
            {(proposal.votes || []).map((v, i) => (
              <tr key={`${v.node_id}-${i}`}>
                <th scope="row">{nodeLabel(v.node_id)}</th>
                <td>
                  <Pill value={v.discard_reason ? "invalid" : v.decision} label={v.discard_reason ? "discarded" : v.decision} />
                </td>
                <td>{v.discard_reason ? `Not counted: ${v.discard_reason}` : v.reason}</td>
                {!compact && <td>{v.signature ? <code className="sig">{v.signature.slice(0, 12)}…</code> : "–"}</td>}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {!compact && nodes.length > 0 && (
        <div className="table-wrap">
          <table className="table table--tight">
            <caption>
              Ledger head on each node before and after this round —{" "}
              <strong>{proposal.ledger_unchanged ? "unchanged" : "changed"}</strong>
            </caption>
            <thead>
              <tr>
                <th scope="col">Node</th>
                <th scope="col">Head before</th>
                <th scope="col">Head after</th>
              </tr>
            </thead>
            <tbody>
              {nodes.map((n) => (
                <tr key={n}>
                  <th scope="row">{nodeLabel(n)}</th>
                  <td>
                    <HashChip hash={proposal.heads_before[n]} />
                  </td>
                  <td>
                    <HashChip hash={proposal.heads_after?.[n]} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {!compact && (
        <>
          <button className="btn btn--ghost btn--small" onClick={() => setShowBlock((s) => !s)} aria-expanded={showBlock}>
            {showBlock ? "Hide proposed block" : "Show proposed block"}
          </button>
          {showBlock && <pre className="json">{JSON.stringify(proposal.block, null, 2)}</pre>}
        </>
      )}
    </div>
  );
}

export function Transactions({ txs }) {
  return (
    <ul className="tx-list">
      {txs.map((tx, i) => (
        <li key={i}>
          <span className={`tx-type tx-type--${tx.type}`}>{tx.type}</span>
          <span className="tx-fields">
            {Object.entries(tx)
              .filter(([k]) => k !== "type")
              .map(([k, v]) => (
                <Fragment key={k}>
                  <span className="tx-key">{k}</span>{" "}
                  <span className="tx-val">{Array.isArray(v) ? v.join(", ") || "none" : String(v)}</span>
                  {"  "}
                </Fragment>
              ))}
          </span>
        </li>
      ))}
    </ul>
  );
}
