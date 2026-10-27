# TrustGrid implementation plan

This plan tracks work in the supplied BlockStore-5 repository plus the TrustGrid master prompt supplied in the
conversation. The actual CS-485 lab manual was not present, so its rubric and course-specific acceptance criteria remain
unverified.

## Phases

| Phase | Work | Status / evidence |
|---|---|---|
| 1. Workspace baseline | Identify the active application, current behavior, tests, and planning material. | Complete. The project is BlockStore-5; its folders contain no Git metadata, and the lab manual is unavailable. |
| 2. Transaction consistency | Validate transactions against committed history and earlier same-block transactions. | Complete. Duplicate file ids and dependent records with an incorrect trusted hash are rejected. |
| 3. Full-ledger semantics | Apply the same validation when verifying whole chains and replacement ledgers. | Complete. Re-hashed but semantically invalid ledgers are rejected. |
| 4. Automatic replica reconciliation | Repair missing/corrupt replicas during node startup/rejoin only from a separate copy verified against the trusted hash. | Complete. Integration tests cover corruption and downtime/rejoin; a correct existing replica is not rewritten. |
| 5. Organization authentication and access | Add configured user accounts, expiring sessions, organization-scoped file access/activity, role checks, sharing and internal node read protection. | Implemented. Backend integration tests cover login, isolation, sharing/revocation, role restrictions, and direct node access. Deployment login depends on explicitly configured accounts. |
| 6. Immutable document versioning | Add version lineage and conflict handling without replacing old bytes or trusted hashes; propagate document sharing across versions. | Implemented. Each version has its own file id/hash and a parent link; ledger validation rejects invalid lineage; stale requests return 409. Regression coverage includes a live upload/version and a competing stale-parent attempt. |
| 7. Traceability and operator guidance | Refresh architecture, setup, limitations, demo, lab mapping, status, plan, and test report. | Complete for this change. The lab mapping is evidence-based, not a claim of rubric compliance. |
| 8. Deployment acceptance | Run authenticated smoke test, persistence/restart walkthrough, and full user-facing demo on a configured deployment. | Not yet verified. No live Docker/local smoke walkthrough has been run for the current authentication/versioning code. |

## Next incomplete work

The next acceptance phase is a configured deployment walkthrough: provide four organization accounts through the documented
environment setting, run the authenticated smoke script, verify rejoin repair and version/share flows through the UI, and
capture actual results. After that, compare this evidence against the CS-485 manual when it is available. Do not label the
system complete before those checks and the remaining security/availability limitations are resolved or explicitly accepted.

## Rules for further work

1. Keep each document version immutable; require the latest parent and reject stale writes instead of silently creating a
   competing branch.
2. Verify new behavior with focused regression tests, then the complete backend and frontend checks that cover affected
   surfaces.
3. Treat SQLite as the trusted-hash anchor and log when automatic repair succeeds without a corresponding quorum-backed
   ledger record.
4. Describe consensus precisely as the implemented coordinator-based signed 3-of-5 vote. Do not call it Raft, PBFT, or
   production Byzantine fault tolerance.
