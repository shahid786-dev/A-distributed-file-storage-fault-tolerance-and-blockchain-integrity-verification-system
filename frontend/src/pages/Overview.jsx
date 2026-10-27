import { ErrorNote, Empty, HashChip, Pill, Section, Spinner, fmtBytes, fmtTime, nodeLabel, usePoll } from "../components/ui.jsx";
import { api } from "../services/api.js";

function Stat({ value, label, tone }) {
  return (
    <div className={`stat${tone ? ` stat--${tone}` : ""}`}>
      <span className="stat__value">{value}</span>
      <span className="stat__label">{label}</span>
    </div>
  );
}

export default function Overview({ go }) {
  const { data: d, error, loading, reload } = usePoll(api.dashboard, 3000);
  const events = usePoll(() => api.events(), 4000);

  if (loading && !d) return <Spinner label="Loading dashboard" />;
  if (!d) return <ErrorNote error={error} onRetry={reload} />;
  const chain = d.blockchain;

  return (
    <>
      <ErrorNote error={error} onRetry={reload} />
      <div className="stats">
        <Stat value={d.total_files} label={`files stored (${fmtBytes(d.total_bytes)})`} />
        <Stat value={`${d.online_nodes}/${d.total_nodes}`} label="nodes online" tone={d.offline_nodes ? "warn" : "ok"} />
        <Stat value={d.offline_nodes} label="nodes offline" tone={d.offline_nodes ? "warn" : undefined} />
        <Stat value={d.verified_replicas} label="verified replicas" tone="ok" />
        <Stat value={d.integrity_failures} label="corrupted replicas detected" tone={d.integrity_failures ? "bad" : undefined} />
        <Stat value={chain.height ?? "–"} label="committed blocks" />
      </div>

      <div className="grid-2">
        <Section title="Ledger agreement" id="ov-ledger"
          aside={<Pill value={chain.has_quorum ? (chain.status === "valid" ? "valid" : "warning") : "invalid"} label={chain.status} />}>
          <p className="lead">
            The committed ledger is the chain that at least 3 of the 5 nodes hold and that passes full validation.
            Current head: <HashChip hash={chain.head_hash} length={16} />
          </p>
          <ul className="state-list">
            {Object.entries(chain.node_states).map(([nid, state]) => (
              <li key={nid}>
                <span>{nodeLabel(nid)}</span>
                <Pill value={state} />
              </li>
            ))}
          </ul>
          <button className="btn btn--ghost btn--small" onClick={() => go("blockchain")}>Open ledger explorer</button>
        </Section>

        <Section title="Latest recovery events" id="ov-recovery">
          {d.latest_recoveries.length === 0 ? (
            <Empty>No recoveries yet. Stop a node or corrupt a replica, then use Recover file.</Empty>
          ) : (
            <ul className="event-mini">
              {d.latest_recoveries.map((e, i) => (
                <li key={i}>
                  <Pill value={e.level} label={e.level} />
                  <span>{e.message}</span>
                  <time>{fmtTime(e.ts)}</time>
                </li>
              ))}
            </ul>
          )}
          {d.malicious_nodes.length > 0 && (
            <p className="warn-text">Malicious test mode is on for: {d.malicious_nodes.map(nodeLabel).join(", ")}</p>
          )}
        </Section>
      </div>

      <Section title="Recent activity" id="ov-events" aside={<button className="btn btn--ghost btn--small" onClick={() => go("events")}>All events</button>}>
        {events.data && events.data.length ? (
          <ul className="event-mini">
            {events.data.slice(0, 8).map((e) => (
              <li key={e.id}>
                <Pill value={e.level} />
                <span>{e.message}</span>
                <time>{fmtTime(e.ts)}</time>
              </li>
            ))}
          </ul>
        ) : (
          <Empty>No activity yet. Start by uploading a file.</Empty>
        )}
      </Section>
    </>
  );
}
