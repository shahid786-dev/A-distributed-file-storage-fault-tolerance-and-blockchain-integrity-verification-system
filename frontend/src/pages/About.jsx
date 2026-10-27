import { Section } from "../components/ui.jsx";

function ArchitectureDiagram() {
  const nodes = [1, 2, 3, 4, 5];
  return (
    <svg className="arch" viewBox="0 0 760 360" role="img" aria-labelledby="arch-title arch-desc">
      <title id="arch-title">BlockStore-5 architecture</title>
      <desc id="arch-desc">Browser dashboard talks to the coordinator backend, which stores metadata in SQLite and talks over HTTP to five storage nodes, each with its own files and ledger copy.</desc>
      <defs>
        <marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
          <path d="M0,0 L10,5 L0,10 z" className="arch__arrowhead" />
        </marker>
      </defs>
      <rect x="20" y="20" width="200" height="64" rx="8" className="arch__box" />
      <text x="120" y="47" className="arch__title">React dashboard</text>
      <text x="120" y="67" className="arch__sub">browser, port 5173</text>

      <rect x="280" y="14" width="250" height="78" rx="8" className="arch__box arch__box--core" />
      <text x="405" y="42" className="arch__title">Coordinator (FastAPI)</text>
      <text x="405" y="62" className="arch__sub">replication, hashing, voting</text>
      <text x="405" y="78" className="arch__sub">port 8000 — single point of failure</text>

      <rect x="590" y="20" width="150" height="64" rx="8" className="arch__box" />
      <text x="665" y="47" className="arch__title">SQLite</text>
      <text x="665" y="67" className="arch__sub">trusted hashes, events</text>

      <line x1="220" y1="52" x2="278" y2="52" className="arch__line" markerEnd="url(#arr)" markerStart="url(#arr)" />
      <line x1="530" y1="52" x2="588" y2="52" className="arch__line" markerEnd="url(#arr)" markerStart="url(#arr)" />

      <text x="405" y="150" className="arch__sub">HTTP: store / fetch files · health · vote · commit · sync</text>
      {nodes.map((i) => {
        const x = 30 + (i - 1) * 146;
        return (
          <g key={i}>
            <line x1="405" y1="92" x2={x + 60} y2="190" className="arch__line" markerEnd="url(#arr)" />
            <rect x={x} y="192" width="120" height="140" rx="8" className="arch__box" />
            <text x={x + 60} y="216" className="arch__title">Node {i}</text>
            <text x={x + 60} y="234" className="arch__sub">port {8000 + i}</text>
            <rect x={x + 12} y="248" width="96" height="30" rx="4" className="arch__chip" />
            <text x={x + 60} y="268" className="arch__sub">file replicas</text>
            <rect x={x + 12} y="286" width="96" height="30" rx="4" className="arch__chip arch__chip--ledger" />
            <text x={x + 60} y="306" className="arch__sub">ledger copy</text>
          </g>
        );
      })}
    </svg>
  );
}

export default function About() {
  return (
    <>
      <Section title="What BlockStore-5 demonstrates" id="about">
        <div className="prose">
          <p>
            One storage server is a single point of failure: if it stops, the file is gone, and if its copy is changed,
            nobody notices. BlockStore-5 stores every file on <strong>five independent nodes</strong>, records the file's
            SHA-256 hash when it is uploaded, and keeps a small <strong>hash-linked ledger</strong> on every node whose
            blocks are only added when at least <strong>3 of 5 nodes vote yes</strong>.
          </p>
          <p>
            If a node stops, files are still read from the others. If one node changes its copy, the coordinator spots
            it by re-hashing the bytes itself, and restores the file from an honest node. If one node proposes a bad
            ledger block, the four honest nodes reject it.
          </p>
        </div>
      </Section>
      <Section title="Architecture" id="arch">
        <ArchitectureDiagram />
      </Section>
      <div className="grid-2 grid-2--top">
        <Section title="Trust model" id="trust">
          <ul className="prose-list">
            <li>The original upload is assumed legitimate. Its SHA-256, calculated by the coordinator, is the trust anchor.</li>
            <li>The trusted hash is written once to SQLite and committed to the ledger. No node can change it.</li>
            <li>A node's claim about its own hash is never trusted: the coordinator downloads the bytes and hashes them.</li>
            <li>Votes are signed with each node's secret key (HMAC-SHA256) and checked against the five registered identities.</li>
          </ul>
        </Section>
        <Section title="Honest limitations" id="limits">
          <ul className="prose-list">
            <li>The coordinator is a single point of failure and could cheat; it is trusted in this prototype.</li>
            <li>Majority voting here is a simplified educational protocol, not production Byzantine fault tolerance.</li>
            <li>One proposal runs at a time; partitions, equivocation and competing proposals are not handled.</li>
            <li>Hash links make tampering detectable, not impossible. Five replicas improve availability but are not a backup.</li>
            <li>Running on one computer shows the idea, not geographic fault tolerance or scalability.</li>
          </ul>
        </Section>
      </div>
    </>
  );
}
