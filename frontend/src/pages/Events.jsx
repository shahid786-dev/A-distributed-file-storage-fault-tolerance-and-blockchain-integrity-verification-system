import { useState } from "react";
import { Empty, ErrorNote, Pill, Section, Spinner, fmtTime, usePoll } from "../components/ui.jsx";
import { api } from "../services/api.js";

const CATEGORIES = ["", "auth", "access", "upload", "version", "download", "integrity", "recovery", "node", "consensus", "simulation"];

export default function Events() {
  const [category, setCategory] = useState("");
  const ev = usePoll(() => api.events(category), 3000, [category]);
  return (
    <Section title="Event log and audit history" id="events"
      aside={
        <label className="control-inline">
          Show{" "}
          <select value={category} onChange={(e) => setCategory(e.target.value)}>
            {CATEGORIES.map((c) => <option key={c} value={c}>{c || "all categories"}</option>)}
          </select>
        </label>
      }>
      <p className="lead">Organization-scoped activity stored by the coordinator in SQLite. Ledger records are separate and live on the five nodes.</p>
      <ErrorNote error={ev.error} onRetry={ev.reload} />
      {!ev.data ? <Spinner /> : ev.data.length === 0 ? <Empty>No events in this category yet.</Empty> : (
        <div className="table-wrap">
          <table className="table table--tight">
            <thead><tr><th scope="col">Time</th><th scope="col">Level</th><th scope="col">Category</th><th scope="col">Event</th></tr></thead>
            <tbody>
              {ev.data.map((e) => (
                <tr key={e.id}>
                  <td className="nowrap">{fmtTime(e.ts)}</td>
                  <td><Pill value={e.level} /></td>
                  <td>{e.category}</td>
                  <td>{e.message}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Section>
  );
}
