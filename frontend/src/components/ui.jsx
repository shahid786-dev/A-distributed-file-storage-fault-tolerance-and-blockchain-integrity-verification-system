// Small shared building blocks for the dashboard.
import { useCallback, useEffect, useRef, useState } from "react";

// Poll an API function every `ms` milliseconds. Keeps the last good data if a poll fails.
export function usePoll(fn, ms = 3000, deps = []) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const fnRef = useRef(fn);
  fnRef.current = fn;

  const reload = useCallback(async () => {
    try {
      const result = await fnRef.current();
      setData(result);
      setError(null);
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    reload();
    if (!ms) return undefined;
    const t = setInterval(reload, ms);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reload, ms, ...deps]);

  return { data, error, loading, reload };
}

// Run a one-off action (button click) with loading + result + error state.
export function useAction() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);
  const run = useCallback(async (fn) => {
    setBusy(true);
    setError(null);
    try {
      const r = await fn();
      setResult(r);
      return r;
    } catch (e) {
      setError(e);
      return null;
    } finally {
      setBusy(false);
    }
  }, []);
  return { busy, error, result, run, setResult, setError };
}

// Each SHA-256 hash gets a colour taken from its first hex digits.
// Equal hashes -> equal colours, so agreement between nodes is visible at a glance.
export function hashHue(hash) {
  if (!hash) return null;
  return parseInt(hash.slice(0, 6), 16) % 360;
}

export function HashChip({ hash, length = 10, title }) {
  if (!hash) return <span className="hash-chip hash-chip--empty">none</span>;
  const hue = hashHue(hash);
  return (
    <span className="hash-chip" title={title || hash} style={{ "--hue": hue }}>
      <span className="hash-chip__swatch" aria-hidden="true" />
      <code>{hash.slice(0, length)}</code>
    </span>
  );
}

const PILL_TONES = {
  online: "ok", match: "ok", consistent: "ok", committed: "ok", accept: "ok", valid: "ok", success: "ok", verified: "ok",
  offline: "down", unavailable: "down", unreachable: "down", "no response": "down", missing: "warn", behind: "warn", warning: "warn",
  mismatch: "bad", invalid: "bad", diverged: "bad", rejected: "bad", reject: "bad", error: "bad", malicious: "bad",
};

export function Pill({ value, label, tone }) {
  const t = tone || PILL_TONES[String(value).toLowerCase()] || "neutral";
  return <span className={`pill pill--${t}`}>{label ?? value}</span>;
}

export function ErrorNote({ error, onRetry }) {
  if (!error) return null;
  return (
    <div className="note note--error" role="alert">
      <strong>{error.status === 0 ? "Backend unreachable." : "Request failed."}</strong> {error.message}
      {onRetry && (
        <button className="btn btn--ghost btn--small" onClick={onRetry}>
          Try again
        </button>
      )}
    </div>
  );
}

export function Note({ tone = "info", children }) {
  return <div className={`note note--${tone}`}>{children}</div>;
}

export function Spinner({ label = "Loading" }) {
  return (
    <span className="spinner" role="status">
      <span className="spinner__dot" aria-hidden="true" />
      {label}…
    </span>
  );
}

export function Button({ busy, children, variant = "primary", small, ...rest }) {
  return (
    <button className={`btn btn--${variant}${small ? " btn--small" : ""}`} disabled={busy || rest.disabled} {...rest}>
      {busy ? <Spinner label="Working" /> : children}
    </button>
  );
}

export function Section({ title, aside, children, id }) {
  return (
    <section className="section" aria-labelledby={id}>
      <header className="section__head">
        <h2 id={id}>{title}</h2>
        {aside && <div className="section__aside">{aside}</div>}
      </header>
      {children}
    </section>
  );
}

export function Empty({ children }) {
  return <p className="empty">{children}</p>;
}

export const fmtBytes = (n) =>
  n == null ? "–" : n < 1024 ? `${n} B` : n < 1048576 ? `${(n / 1024).toFixed(1)} KB` : `${(n / 1048576).toFixed(2)} MB`;

export const fmtTime = (iso) => {
  if (!iso) return "–";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString();
};

export const nodeLabel = (id) => (id ? id.replace("node", "Node ") : id);
