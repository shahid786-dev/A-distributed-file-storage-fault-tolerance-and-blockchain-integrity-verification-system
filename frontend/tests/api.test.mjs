// Requirement 17: the dashboard turns unavailable services and API errors into clear messages.
// Run with:  npm test   (uses Node's built-in test runner, no extra packages)
import assert from "node:assert/strict";
import { test } from "node:test";
import { api, ApiError } from "../src/services/api.js";

function fakeFetch(status, body) {
  globalThis.fetch = async () => ({ ok: status < 400, status, text: async () => JSON.stringify(body) });
}

test("backend unreachable -> status 0 and a readable message", async () => {
  globalThis.fetch = async () => { throw new TypeError("fetch failed"); };
  await assert.rejects(api.nodes(), (e) => e instanceof ApiError && e.status === 0 && /Cannot reach the backend/.test(e.message));
});

test("503 with a string detail is shown as-is", async () => {
  fakeFetch(503, { detail: "fewer than 3 nodes hold the same valid ledger - cannot propose" });
  await assert.rejects(api.verify("a".repeat(32)), (e) => e.status === 503 && /fewer than 3 nodes/.test(e.message));
});

test("422 validation errors become one sentence", async () => {
  fakeFetch(422, { detail: [{ loc: ["body", "node_id"], msg: "Input should be 'node1'" }] });
  await assert.rejects(api.setMalicious("node9", true), (e) => e.message === "node_id: Input should be 'node1'");
});

test("object detail (download with no verified replica) uses its message", async () => {
  fakeFetch(503, { detail: { message: "No verified replica is available", attempts: [] } });
  await assert.rejects(api.recover("a".repeat(32)), (e) => e.message === "No verified replica is available");
});

test("successful responses are returned unchanged", async () => {
  fakeFetch(200, [{ node_id: "node1", online: true }]);
  assert.deepEqual(await api.nodes(), [{ node_id: "node1", online: true }]);
});

test("login token is sent and cleared when browser session storage is unavailable", async () => {
  const originalStorage = Object.getOwnPropertyDescriptor(globalThis, "sessionStorage");
  Object.defineProperty(globalThis, "sessionStorage", {
    configurable: true,
    get() { throw new DOMException("Storage is unavailable", "SecurityError"); },
  });
  const requests = [];
  globalThis.fetch = async (_url, options) => {
    requests.push(options);
    const login = requests.length === 1;
    return {
      ok: true,
      status: 200,
      text: async () => JSON.stringify(login ? { access_token: "session-token" } : { user_id: "user-1" }),
    };
  };

  try {
    await api.login("manufacturer", "user@example.test", "password");
    await api.me();
    assert.equal(requests[1].headers.Authorization, ["Bearer", "session-token"].join(" "));
    await api.logout();
    await api.me();
    assert.equal(requests[3].headers.Authorization, undefined);
  } finally {
    api.clearSession();
    if (originalStorage) Object.defineProperty(globalThis, "sessionStorage", originalStorage);
    else delete globalThis.sessionStorage;
  }
});
