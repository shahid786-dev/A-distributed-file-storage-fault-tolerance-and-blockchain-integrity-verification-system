# Evidence-based lab topic mapping

The exact CS-485 lab manual was not present in the workspace or session files. The table below maps broad distributed
systems topics visible in this repository to implementation evidence. It is **not** a claim that the project satisfies
any unavailable course rubric.

| Topic | Repository implementation | Verification evidence | Boundary / limitation |
|---|---|---|---|
| Replication and availability | Five independent HTTP storage-node processes/containers; write quorum of three. | Backend upload, node failure, download and rejoin integration cases. | All nodes may still share one host/disk in a local demonstration. |
| Integrity and trusted data | Coordinator-calculated SHA-256 anchors each immutable file version; downloads re-hash bytes. | Hash mismatch, verified-source recovery, version-hash integration checks. | Coordinator metadata is trusted; no external trust-anchor protection. |
| Hash-linked ledger | Deterministic blocks, previous-hash links, common shared validation code, whole-chain validation. | Blockchain unit tests, ledger tampering/replacement and convergence integration tests. | A custom educational ledger, not a public chain or proof-of-work protocol. |
| Transaction state invariants | Transactions see committed history and earlier transactions in their block; version records must extend the latest parent. | Same-block, forged/re-hashed history and document-version unit tests. | The coordinator still serializes proposal rounds and is trusted. |
| Consensus and voting | Coordinator gathers per-node HMAC-signed votes and commits at 3-of-5 accepts. | Quorum, invalid-block rejection, signature and convergence tests. | Not Raft, PBFT, or formally proven BFT; see [limitations.md](./limitations.md). |
| Fault detection and repair | Health polling, ledger catch-up, and rejoin reconciliation from a distinct source matching the trusted hash. | Real node process integration tests cover missed/corrupt replica repair. | Repaired bytes may not receive a ledger record if quorum is unavailable; the omission is logged. |
| Identity and authorization | Configured organizations/users, expiring bearer sessions, role checks, document ownership and explicit read shares. | Integration tests for unauthenticated requests, isolation, sharing/revocation, roles, and node control token. | No MFA, TLS deployment, rate limiting, or external identity provider. |
| Versioning and conflict handling | Separate file id/hash per version, logical document id, sequential number and parent; stale parent rejected. | Version endpoint integration and chain validation regressions. | No version retention policy, independent backup, or multi-coordinator conflict protocol. |
| Client / operator interface | React dashboard pages for files, nodes, ledger, events, login and sharing. | Frontend API tests and Vite production build. | No current post-change live browser walkthrough; deployment check remains open. |

For a rubric-level mapping, obtain the manual and replace these broad topics with its exact requirement text, acceptance
criteria, and evidence. Do not infer scores or course compliance from this table.
