# TrustGrid feature status

**Workspace:** BlockStore-5  
**Scope:** Status is based on source inspection and tests in this workspace. The exact CS-485 lab manual was not
available; the project must not be described as course-certified or complete on that basis.

## Implemented and verified

| Area | Result | Evidence |
|---|---|---|
| Replicated files and integrity | Five-node replication, trusted coordinator SHA-256, verified downloads, integrity checks, and recovery. | Backend integration suite. |
| Block-local transaction validation | A proposed transaction is checked against committed history and earlier transactions in the same block. Duplicate file registrations and invalid dependent hashes are rejected. | Blockchain unit regressions. |
| Full-ledger validation | Each block is semantically validated against the prefix preceding it, including during whole-chain validation. | Re-hashed semantically invalid ledger regression. |
| Organization authentication | Four organizations, PBKDF2-SHA256 password hashes, expiring opaque bearer sessions, logout/revocation, member/admin checks, and organization-scoped activity. | Backend login, isolation, role, and node-access integration tests. |
| File sharing | Owners can grant/revoke read access; server checks govern file routes, and shared files remain read-only. Sharing applies across the document's versions. | Backend organization-sharing tests, including revocation. |
| Replica rejoin repair | Startup/rejoin reconciliation checks against SQLite's trusted hash; repairs only from a different verified source, then rereads/re-hashes the target. | Backend node-rejoin and corruption integration tests. |
| Immutable document versions | Each version has its own file id and trusted hash, a stable document id, sequential number and parent link. The chain records `FILE_VERSION_CREATED`; stale-parent requests receive HTTP 409 rather than overwriting or silently forking history. | Blockchain version-validation tests and live-cluster version, stale-parent, lineage, and share tests. |
| Frontend session/API behavior | Bearer headers, login/logout cleanup, readable API errors, and an in-memory token fallback when browser session storage is unavailable. | Node test runner; production Vite build. |
| Smoke/benchmark login | Both scripts accept organization/email/password flags or environment variables and prompt for missing credentials. | Python syntax checks and `--help` execution; no live smoke run in this verification. |

## Latest verification

| Check | Result |
|---|---|
| Focused blockchain + database migration unit tests | 17 passed. |
| Complete backend unit + live-cluster suite | 45 passed in 61.18 s. |
| Frontend unit tests | 6 passed, including session storage denial fallback. |
| Frontend production build | Passed with Vite 6.4.5. |
| Smoke test / Docker | Not run against a configured live demo deployment in this verification. |

Passing automated tests do not establish that the entire TrustGrid project or any unavailable lab rubric is complete.

## Remaining work

- Obtain and map the actual CS-485 manual against implementation and acceptance evidence; [LAB_MAPPING.md](./LAB_MAPPING.md)
  distinguishes verified repository evidence from unavailable rubric claims.
- Run the updated authenticated smoke test against a configured local/Docker deployment and perform the revised UI demo.
- Exercise authentication migrations and fresh deployment configuration against a durable non-test database in a dedicated
  deployment smoke test; regression coverage currently exercises SQLite version-column migration.
- Review and document deployment secrets, transport security, backup/restore, and the limits of the coordinator-based
  3-of-5 vote protocol. This remains an educational prototype, not production BFT.
