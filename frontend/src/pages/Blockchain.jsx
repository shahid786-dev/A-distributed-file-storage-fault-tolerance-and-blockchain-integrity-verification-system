import { useState } from "react";
import { ProposalView, Transactions } from "../components/Results.jsx";
import { Button, Empty, ErrorNote, HashChip, Note, Pill, Section, Spinner, fmtTime, nodeLabel, useAction, usePoll } from "../components/ui.jsx";
import { api } from "../services/api.js";

function Validation({ isAdmin }) {
  const v = usePoll(api.validate, 4000);
  const repair = useAction();
  const d = v.data;
  const broken = d && Object.values(d.nodes).some((n) => ["behind", "invalid", "diverged"].includes(n.state));
  return (
    <Section title="Ledger validation" id="validation"
      aside={
        <div className="btn-row">
          <Button small variant="secondary" onClick={v.reload}>Validate now</Button>
          {isAdmin && <Button small disabled={!broken} busy={repair.busy}
            onClick={() => repair.run(api.repairLedgers).then(v.reload)}>Repair inconsistent copies</Button>}
        </div>
      }>
      <p className="lead">
        For every node the coordinator recalculates each block hash, checks the previous-hash links and sequential
        indexes, validates transactions against earlier committed and same-block history, and compares the head with
        the majority. Hash links make tampering <em>detectable</em>; they do not stop someone who controls a copy from
        rewriting it.
      </p>
      <ErrorNote error={v.error || repair.error} />
      {repair.result && <Note tone="ok">Repaired {repair.result.repaired.length} node(s) from the majority ledger. Status now: {repair.result.after.status}.</Note>}
      {!d ? <Spinner /> : (
        <div className="table-wrap">
          <table className="table">
            <caption>
              Overall: <Pill value={d.status === "valid" ? "valid" : d.has_quorum ? "warning" : "invalid"} label={d.status} /> — committed
              height {d.committed_height ?? "–"}, agreed by {d.agreeing_nodes.length} of 5 nodes. Checked {fmtTime(d.checked_at)}.
            </caption>
            <thead><tr><th scope="col">Node</th><th scope="col">State</th><th scope="col">Height</th><th scope="col">Head hash</th><th scope="col">Problems found</th></tr></thead>
            <tbody>
              {Object.entries(d.nodes).map(([nid, n]) => (
                <tr key={nid} className={n.state === "invalid" || n.state === "diverged" ? "row--bad" : ""}>
                  <th scope="row">{nodeLabel(nid)}</th>
                  <td><Pill value={n.state} /></td>
                  <td>{n.height ?? "–"}</td>
                  <td><HashChip hash={n.head_hash} /></td>
                  <td>{n.detail || (n.errors.length ? n.errors.map((e) => `block ${e.index}: ${e.problem}`).join("; ") : "none")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Section>
  );
}

function BlockList() {
  const b = usePoll(api.blocks, 5000);
  const [open, setOpen] = useState({});
  const blocks = b.data?.blocks || [];
  return (
    <Section title="Committed blocks" id="blocks" aside={<span className="muted">newest first</span>}>
      <ErrorNote error={b.error} onRetry={b.reload} />
      {!b.data ? <Spinner /> : !b.data.has_quorum ? (
        <Empty>No 3 nodes currently agree on a valid ledger, so there is no committed chain to show.</Empty>
      ) : (
        <ol className="chain">
          {blocks.map((blk) => (
            <li key={blk.hash} className="block">
              <button className="block__head" onClick={() => setOpen((o) => ({ ...o, [blk.index]: !o[blk.index] }))} aria-expanded={!!open[blk.index]}>
                <span className="block__index">#{blk.index}</span>
                <span className="block__types">{blk.transactions.map((t) => t.type).join(", ")}</span>
                <span className="block__by">{blk.proposer}</span>
                <time>{fmtTime(blk.timestamp)}</time>
              </button>
              <div className="block__hashes">
                <span>hash <HashChip hash={blk.hash} length={16} /></span>
                <span>previous <HashChip hash={blk.previous_hash} length={16} /></span>
              </div>
              {open[blk.index] && <Transactions txs={blk.transactions} />}
            </li>
          ))}
        </ol>
      )}
    </Section>
  );
}

function Proposals() {
  const p = usePoll(api.proposals, 6000);
  return (
    <Section title="Recent votes" id="proposals">
      <ErrorNote error={p.error} />
      {!p.data ? <Spinner /> : p.data.length === 0 ? <Empty>No proposals yet.</Empty> : (
        <div className="stack">{p.data.slice(0, 4).map((x) => <ProposalView key={x.proposal_id} proposal={x} compact />)}</div>
      )}
    </Section>
  );
}

export default function Blockchain({ isAdmin }) {
  return (
    <>
      <Validation isAdmin={isAdmin} />
      <BlockList />
      <Proposals />
    </>
  );
}
