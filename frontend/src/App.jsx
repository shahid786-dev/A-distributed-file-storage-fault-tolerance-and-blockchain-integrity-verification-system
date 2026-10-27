import { useEffect, useState } from "react";
import NodeRail from "./components/NodeRail.jsx";
import { Spinner, usePoll } from "./components/ui.jsx";
import About from "./pages/About.jsx";
import AttackLab from "./pages/AttackLab.jsx";
import Blockchain from "./pages/Blockchain.jsx";
import Events from "./pages/Events.jsx";
import Files from "./pages/Files.jsx";
import Login from "./pages/Login.jsx";
import Nodes from "./pages/Nodes.jsx";
import Overview from "./pages/Overview.jsx";
import { api } from "./services/api.js";

const PAGES = [
  { id: "overview", label: "Overview", title: "System overview" },
  { id: "files", label: "Files", title: "Files, replication and integrity" },
  { id: "nodes", label: "Nodes", title: "Node monitoring and failure" },
  { id: "blockchain", label: "Ledger", title: "Blockchain ledger explorer" },
  { id: "attack", label: "Attack lab", title: "Malicious-node simulation" },
  { id: "events", label: "Events", title: "Events and audit history" },
  { id: "about", label: "About", title: "Architecture and project information" },
];

// Tiny hash router (#/files etc.) so pages can be bookmarked without extra libraries.
function useHashPage() {
  const read = () => (window.location.hash.replace("#/", "") || "overview");
  const [page, setPage] = useState(read);
  useEffect(() => {
    const on = () => setPage(read());
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  const go = (id) => { window.location.hash = `/${id}`; };
  return [PAGES.some((p) => p.id === page) ? page : "overview", go];
}

export default function App() {
  const [user, setUser] = useState(null);
  const [authReady, setAuthReady] = useState(false);
  const [logoutNotice, setLogoutNotice] = useState("");

  useEffect(() => {
    api.me().then(setUser).catch(() => api.clearSession()).finally(() => setAuthReady(true));
  }, []);

  if (!authReady) return <main className="login-shell"><Spinner label="Checking session" /></main>;
  if (!user) return <Login onLogin={setUser} notice={logoutNotice} />;
  return <Dashboard user={user} onLogout={async () => {
    try {
      await api.logout();
    } catch (error) {
      setLogoutNotice(`Signed out locally, but the server could not revoke the session: ${error.message}`);
    } finally {
      api.clearSession();
      setUser(null);
    }
  }} />;
}

function Dashboard({ user, onLogout }) {
  const [page, go] = useHashPage();
  const nodes = usePoll(api.nodes, 2500);
  const effectivePage = user.role === "admin" || page !== "attack" ? page : "overview";
  const current = PAGES.find((p) => p.id === effectivePage);
  const backendDown = nodes.error && nodes.error.status === 0;

  return (
    <div className="shell">
      <aside className="sidebar">
        <a className="brand" href="#/overview" aria-label="BlockStore-5 home">
          <span className="brand__mark" aria-hidden="true">{[0, 1, 2, 3, 4].map((i) => <i key={i} />)}</span>
          <span className="brand__name">TrustGrid</span>
        </a>
        <nav aria-label="Main">
          <ul>
            {PAGES.filter((p) => user.role === "admin" || p.id !== "attack").map((p) => (
              <li key={p.id}>
                <a href={`#/${p.id}`} aria-current={p.id === page ? "page" : undefined}
                  className={p.id === "attack" ? "nav-test" : undefined}>{p.label}</a>
              </li>
            ))}
          </ul>
        </nav>
        <div className="account-card">
          <strong>{user.organization_name}</strong>
          <span>{user.email} · {user.role}</span>
          <button className="btn btn--ghost btn--small" onClick={onLogout}>Sign out</button>
        </div>
        <p className="sidebar__foot">Cloud and Distributed Computing CEP. Educational prototype.</p>
      </aside>

      <main className="main">
        {backendDown && (
          <div className="banner" role="alert">
            The dashboard cannot reach the coordinator backend. Start it (<code>python run_local.py start</code> or{" "}
            <code>docker compose up</code>) and this page will reconnect automatically.
          </div>
        )}
        <NodeRail nodes={nodes.data} error={nodes.error} />
        <h1 className="page-title">{current.title}</h1>
        {effectivePage === "overview" && <Overview go={go} />}
        {effectivePage === "files" && <Files user={user} />}
        {effectivePage === "nodes" && <Nodes nodes={nodes.data} error={nodes.error} refresh={nodes.reload} isAdmin={user.role === "admin"} />}
        {effectivePage === "blockchain" && <Blockchain isAdmin={user.role === "admin"} />}
        {effectivePage === "attack" && <AttackLab nodes={nodes.data} refresh={nodes.reload} />}
        {effectivePage === "events" && <Events />}
        {effectivePage === "about" && <About />}
      </main>
    </div>
  );
}
