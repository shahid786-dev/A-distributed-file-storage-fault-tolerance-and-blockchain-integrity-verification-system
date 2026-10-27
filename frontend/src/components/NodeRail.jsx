// The strip of five nodes shown at the top of every page.
// Matching hash colours = nodes agree on the same ledger head.
import { HashChip, Pill, nodeLabel } from "./ui.jsx";

export default function NodeRail({ nodes, error }) {
  if (!nodes) {
    return (
      <div className="rail rail--loading" aria-busy="true">
        {error ? error.message : "Checking the five nodes…"}
      </div>
    );
  }
  const online = nodes.filter((n) => n.online);
  const heads = online.map((n) => n.ledger_head_hash);
  const top = heads.sort((a, b) => heads.filter((h) => h === b).length - heads.filter((h) => h === a).length)[0];
  const agreeing = online.filter((n) => n.ledger_head_hash === top).length;

  return (
    <div className="rail" aria-label="Live state of the five storage nodes">
      <ol className="rail__nodes">
        {nodes.map((n) => (
          <li
            key={n.node_id}
            className={`rail-node${n.online ? "" : " rail-node--down"}${n.malicious_simulation ? " rail-node--evil" : ""}`}
          >
            <div className="rail-node__top">
              <strong>{nodeLabel(n.node_id)}</strong>
              <Pill value={n.online ? "online" : "offline"} />
            </div>
            {n.online ? (
              <>
                <HashChip hash={n.ledger_head_hash} length={8} title={`Ledger head ${n.ledger_head_hash}`} />
                <span className="rail-node__meta">
                  {n.ledger_height} blocks · {n.file_count} files
                </span>
              </>
            ) : (
              <span className="rail-node__meta rail-node__meta--err">{n.last_error || "not responding"}</span>
            )}
            {n.malicious_simulation && <span className="rail-node__flag">Malicious test mode</span>}
            {n.corrupted_replicas > 0 && (
              <span className="rail-node__flag rail-node__flag--soft">{n.corrupted_replicas} bad replica(s)</span>
            )}
          </li>
        ))}
      </ol>
      <p className="rail__summary">
        <span>
          <strong>{online.length}/5</strong> online
        </span>
        <span>
          <strong>{agreeing}/5</strong> share the same ledger head
        </span>
        <span className={online.length >= 3 ? "" : "rail__warn"}>
          {online.length >= 3 ? "Quorum of 3 available" : "No quorum: uploads and commits are blocked"}
        </span>
      </p>
    </div>
  );
}
