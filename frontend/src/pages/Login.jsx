import { useState } from "react";
import { api } from "../services/api.js";
import { ErrorNote, Spinner, useAction, usePoll } from "../components/ui.jsx";

export default function Login({ onLogin, notice }) {
  const organizations = usePoll(api.organizations, 0);
  const action = useAction();
  const [organization, setOrganization] = useState("manufacturer");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  async function submit(event) {
    event.preventDefault();
    const result = await action.run(() => api.login(organization, email, password));
    if (result) onLogin(result.user);
  }

  return (
    <main className="login-shell">
      <section className="login-card" aria-labelledby="login-title">
        <div className="brand brand--login">
          <span className="brand__mark" aria-hidden="true">{[0, 1, 2, 3, 4].map((i) => <i key={i} />)}</span>
          <span className="brand__name">TrustGrid</span>
        </div>
        <h1 id="login-title">Organization sign in</h1>
        <p className="muted">Use the account provisioned for your supply-chain organization.</p>
        {notice && <p className="note note--warn" role="status">{notice}</p>}
        <ErrorNote error={action.error || organizations.error} onRetry={organizations.reload} />
        {!organizations.data ? <Spinner label="Loading organizations" /> : (
          <form className="login-form" onSubmit={submit}>
            <label>
              Organization
              <select value={organization} onChange={(event) => setOrganization(event.target.value)}>
                {organizations.data.map((item) => (
                  <option key={item.id} value={item.id}>{item.name}</option>
                ))}
              </select>
            </label>
            <label>
              Email
              <input type="email" autoComplete="username" required value={email}
                onChange={(event) => setEmail(event.target.value)} />
            </label>
            <label>
              Password
              <input type="password" autoComplete="current-password" required value={password}
                onChange={(event) => setPassword(event.target.value)} />
            </label>
            <button className="btn btn--primary" type="submit" disabled={action.busy}>
              {action.busy ? <Spinner label="Signing in" /> : "Sign in"}
            </button>
          </form>
        )}
      </section>
    </main>
  );
}
