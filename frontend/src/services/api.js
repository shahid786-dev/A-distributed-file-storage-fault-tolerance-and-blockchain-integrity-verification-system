// All calls from the dashboard to the coordinator backend live here.
// Every function returns real data from the backend; nothing is mocked.

const BASE = "/api";
let memoryToken = null;

export class ApiError extends Error {
  constructor(message, status, body) {
    super(message);
    this.status = status;
    this.body = body;
  }
}

function browserSessionStorage() {
  try {
    return globalThis.sessionStorage || null;
  } catch {
    return null;
  }
}

function authorizationHeader() {
  let token = memoryToken;
  try {
    token = browserSessionStorage()?.getItem("trustgrid-token") || memoryToken;
  } catch {
    // Fall back to the in-memory session when browser storage is unavailable.
  }
  return token ? { Authorization: ["Bearer", token].join(" ") } : {};
}

function storeToken(token) {
  memoryToken = token;
  try {
    browserSessionStorage()?.setItem("trustgrid-token", token);
  } catch {
    // The token remains usable for this page lifetime.
  }
}

function clearToken() {
  memoryToken = null;
  try {
    browserSessionStorage()?.removeItem("trustgrid-token");
  } catch {
    // Local sign-out still takes effect for this page lifetime.
  }
}

// Turn FastAPI error bodies (strings, objects or validation lists) into one readable sentence.
function describeError(body, status) {
  const d = body && body.detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d)) return d.map((e) => `${(e.loc || []).slice(1).join(".")}: ${e.msg}`).join("; ");
  if (d && typeof d === "object") return d.message || JSON.stringify(d);
  if (body && body.message) return body.message;
  return `Request failed with HTTP ${status}`;
}

async function request(path, { method = "GET", json, body } = {}) {
  let res;
  try {
    res = await fetch(BASE + path, {
      method,
      headers: {
        ...authorizationHeader(),
        ...(json ? { "Content-Type": "application/json" } : {}),
      },
      body: json ? JSON.stringify(json) : body,
    });
  } catch {
    throw new ApiError("Cannot reach the backend. Check that it is running on port 8000.", 0, null);
  }
  const text = await res.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = { detail: text.slice(0, 200) };
  }
  if (!res.ok) throw new ApiError(describeError(data, res.status), res.status, data);
  return data;
}

const post = (path, json) => request(path, { method: "POST", json });

export const api = {
  organizations: () => request("/auth/organizations"),
  login: async (organization, email, password) => {
    const result = await post("/auth/login", { organization, email, password });
    storeToken(result.access_token);
    return result;
  },
  me: () => request("/auth/me"),
  logout: async () => {
    try {
      return await post("/auth/logout", {});
    } finally {
      clearToken();
    }
  },
  clearSession: clearToken,
  health: () => request("/health"),
  dashboard: () => request("/dashboard"),
  events: (category) => request(`/events?limit=150${category ? `&category=${category}` : ""}`),

  files: () => request("/files"),
  file: (id) => request(`/files/${id}`),
  shares: (id) => request(`/files/${id}/shares`),
  share: (id, organization) => post(`/files/${id}/shares`, { organization, permission: "read" }),
  revokeShare: (id, organization) => request(`/files/${id}/shares/${organization}`, { method: "DELETE" }),
  replicas: (id) => request(`/files/${id}/replicas`),
  verify: (id) => post(`/files/${id}/verify`),
  recover: (id) => post(`/files/${id}/recover`),
  upload: (file) => {
    const form = new FormData();
    form.append("file", file);
    return request("/files/upload", { method: "POST", body: form });
  },
  uploadVersion: (fileId, expectedVersion, file) => {
    const form = new FormData();
    form.append("file", file);
    return request(`/files/${fileId}/versions?expected_version=${expectedVersion}`,
      { method: "POST", body: form });
  },

  // Download goes through the coordinator, which only returns a copy whose hash it verified.
  download: async (id, name) => {
    let res;
    try {
      res = await fetch(`${BASE}/files/${id}/download`, { headers: authorizationHeader() });
    } catch {
      throw new ApiError("Cannot reach the backend.", 0, null);
    }
    if (!res.ok) {
      const data = await res.json().catch(() => null);
      throw new ApiError(describeError(data, res.status), res.status, data);
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = name;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 2000);
    return {
      sourceNode: res.headers.get("X-BlockStore-Source-Node"),
      verifiedHash: res.headers.get("X-BlockStore-Verified-SHA256"),
      skipped: res.headers.get("X-BlockStore-Skipped"),
      size: blob.size,
    };
  },

  nodes: () => request("/nodes"),
  nodeFiles: (id) => request(`/nodes/${id}/files`),

  blocks: () => request("/blockchain/blocks"),
  validate: () => request("/blockchain/validate"),
  proposals: () => request("/blockchain/proposals?limit=15"),
  repairLedgers: () => post("/blockchain/repair"),

  failNode: (node_id) => post("/simulation/node-failure", { node_id }),
  restartNode: (node_id) => post("/simulation/node-restart", { node_id }),
  setMalicious: (node_id, enabled) => post("/simulation/malicious-node", { node_id, enabled }),
  corruptReplica: (node_id, file_id) => post("/simulation/corrupt-replica", { node_id, file_id, confirm: true }),
  invalidBlock: (node_id, attack, file_id) => post("/simulation/invalid-block", { node_id, attack, file_id }),
  tamperLedger: (node_id) => post("/simulation/tamper-ledger", { node_id, confirm: true }),
};
