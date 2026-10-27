import { useEffect, useState } from "react";
import { IntegrityTable, ProposalView, SummaryLine } from "../components/Results.jsx";
import { Button, Empty, ErrorNote, Note, Pill, Section, nodeLabel, useAction, usePoll } from "../components/ui.jsx";
import { api } from "../services/api.js";

const NODE_IDS = ["node1", "node2", "node3", "node4", "node5"];
const ATTACKS = {
  wrong_previous_hash: "Wrong previous hash — the block does not link to the committed head",
  bad_block_hash: "Bad block hash — the content was edited after the hash was calculated",
  overwrite_trusted_hash: "Overwrite trusted hash — a well-formed block that re-registers an existing file with a new hash",
};

function Step({ n, title, children }) {
  return (
    <li className="step">
      <span className="step__n" aria-hidden="true">{n}</span>
      <div className="step__body">
        <h3>{title}</h3>
        {children}
      </div>
    </li>
  );
}

export default function AttackLab({ nodes, refresh }) {
  const files = usePoll(api.files, 0);
  const [nodeId, setNodeId] = useState("node3");
  const [fileId, setFileId] = useState("");
  const [attack, setAttack] = useState("wrong_previous_hash");
  const mal = useAction();
  const corrupt = useAction();
  const check = useAction();
  const rec = useAction();
  const prop = useAction();
  const tamper = useAction();

  useEffect(() => {
    if (!fileId && files.data?.length) setFileId(files.data[0].file_id);
  }, [files.data, fileId]);

  const node = nodes?.find((n) => n.node_id === nodeId);
  const malicious = !!node?.malicious_simulation;

  const toggleMalicious = async () => {
    await mal.run(() => api.setMalicious(nodeId, !malicious));
    refresh();
  };
  const doCorrupt = async () => {
    if (!window.confirm(`TEST OPERATION: change the bytes of ${nodeLabel(nodeId)}'s copy of this file? The other four copies are not touched.`)) return;
    await corrupt.run(() => api.corruptReplica(nodeId, fileId));
    refresh();
  };
  const doTamper = async () => {
    if (!window.confirm(`TEST OPERATION: edit a past block inside ${nodeLabel(nodeId)}'s local ledger file?`)) return;
    await tamper.run(() => api.tamperLedger(nodeId));
    refresh();
  };
  const recResult = rec.result
    ? { ...rec.result, replicas: rec.result.replicas_after, summary: rec.result.summary_after }
    : null;

  return (
    <>
      <Note tone="warn">
        <strong>Test area.</strong> Everything on this page is a predefined simulation on the project's own sample data.
        Malicious mode is held in memory only: turning it off, or restarting the node, makes the node honest again.
      </Note>

      <Section title="Choose the malicious node" id="lab-node">
        <div className="control-row">
          <label htmlFor="lab-node-select">Node under test</label>
          <select id="lab-node-select" value={nodeId} onChange={(e) => setNodeId(e.target.value)}>
            {NODE_IDS.map((n) => <option key={n} value={n}>{nodeLabel(n)}</option>)}
          </select>
          <Pill value={malicious ? "malicious" : "online"} label={malicious ? "malicious test mode on" : "honest"} />
          <Button variant={malicious ? "secondary" : "danger"} busy={mal.busy} onClick={toggleMalicious} disabled={!node?.online}>
            {malicious ? "Disable malicious simulation" : "Enable malicious simulation"}
          </Button>
        </div>
        <ErrorNote error={mal.error} />
        <p className="muted">
          In malicious mode the node accepts every proposal without checking, lies about its file hashes, and unlocks the
          tampering actions below.
        </p>
      </Section>

      <div className="grid-2 grid-2--top">
        <Section title="Attack A: tamper with a stored file" id="lab-a">
          {files.data && files.data.length === 0 ? <Empty>Upload a file on the Files page first.</Empty> : (
            <ol className="steps">
              <Step n={1} title="Pick a file">
                <select aria-label="File to attack" value={fileId} onChange={(e) => setFileId(e.target.value)}>
                  {(files.data || []).map((f) => <option key={f.file_id} value={f.file_id}>{f.name}</option>)}
                </select>
              </Step>
              <Step n={2} title={`Modify only ${nodeLabel(nodeId)}'s copy`}>
                <Button variant="danger" busy={corrupt.busy} disabled={!malicious || !fileId} onClick={doCorrupt}>Corrupt test replica</Button>
                {!malicious && <p className="muted">Enable malicious simulation first.</p>}
                <ErrorNote error={corrupt.error} />
                {corrupt.result && <Note tone="warn">{nodeLabel(nodeId)} added {corrupt.result.bytes_added} bytes to its copy. The trusted hash was not changed.</Note>}
              </Step>
              <Step n={3} title="Run integrity check on all five nodes">
                <Button busy={check.busy} disabled={!fileId} onClick={() => check.run(() => api.verify(fileId)).then(refresh)}>Run integrity verification</Button>
                <ErrorNote error={check.error} />
              </Step>
              <Step n={4} title="Recover from an honest node">
                <Button variant="secondary" busy={rec.busy} disabled={!fileId} onClick={() => rec.run(() => api.recover(fileId)).then(refresh)}>Recover original file</Button>
                <ErrorNote error={rec.error} />
                {rec.result && (
                  <Note tone="ok">
                    Verified copy taken from {nodeLabel(rec.result.source_node)}.{" "}
                    {rec.result.repaired_nodes.length ? `Re-replicated to ${rec.result.repaired_nodes.map(nodeLabel).join(", ")}.` : "Nothing needed repair."}
                  </Note>
                )}
              </Step>
            </ol>
          )}
        </Section>

        <Section title="Attack B: propose an invalid block" id="lab-b">
          <ol className="steps">
            <Step n={1} title="Choose the kind of invalid block">
              <select aria-label="Kind of invalid block" value={attack} onChange={(e) => setAttack(e.target.value)}>
                {Object.entries(ATTACKS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
            </Step>
            <Step n={2} title={`${nodeLabel(nodeId)} sends it to all five nodes for a vote`}>
              <Button variant="danger" busy={prop.busy} disabled={!malicious} onClick={() => prop.run(() => api.invalidBlock(nodeId, attack, fileId || null)).then(refresh)}>
                Submit invalid block proposal
              </Button>
              {!malicious && <p className="muted">Enable malicious simulation first.</p>}
              <ErrorNote error={prop.error} />
            </Step>
          </ol>
          <h3 className="sub">Bonus: edit this node's own ledger copy</h3>
          <p className="muted">Changes a past block on disk without recalculating its hash. Then open the Ledger page and validate.</p>
          <Button small variant="danger" busy={tamper.busy} disabled={!malicious} onClick={doTamper}>Tamper with local ledger</Button>
          <ErrorNote error={tamper.error} />
          {tamper.result && <Note tone={tamper.result.ok ? "warn" : "info"}>{tamper.result.ok ? `Block #${tamper.result.block_index} field "${tamper.result.field}" was edited on ${nodeLabel(nodeId)}.` : tamper.result.detail}</Note>}
        </Section>
      </div>

      {(recResult || check.result) && (
        <Section title={recResult ? "Replica status after recovery" : "Integrity check result"} id="lab-integrity">
          <SummaryLine summary={(recResult || check.result).summary} />
          <IntegrityTable report={recResult || check.result} />
        </Section>
      )}

      {prop.result && (
        <Section title="Voting result for the invalid proposal" id="lab-votes">
          <p className="lead">{prop.result.description}.</p>
          <ProposalView proposal={prop.result.proposal} />
        </Section>
      )}
    </>
  );
}
