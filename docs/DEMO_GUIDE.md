# TrustGrid / BlockStore-5 demo guide

This guide is for the current implementation in the repository. It does not replace a course rubric; the actual CS-485
manual was unavailable during this update.

## Before the demo

1. Copy `.env.example` to `.env`.
2. Replace node vote secrets and `CONTROL_TOKEN`.
3. Configure `TRUSTGRID_DEMO_USERS` with four distinct organization accounts (at least 12 characters per password).
   Follow the JSON example in [setup.md](./setup.md). Do not commit real credentials.
4. Start with `docker compose up --build -d` or use local mode. Wait until all five nodes are online.
5. Sign in to the dashboard as the Engro Corporation administrator.

Existing accounts are insert-only: changing the environment variable does not replace a stored account's password.

## Suggested walkthrough

1. **System status:** show the five node health cards, coordinator status, and that the ledger copies agree.
2. **Upload version 1:** upload a small supported document; show its id, SHA-256, replication result and committed
   ledger block. Explain that the coordinator recalculates the hash of node replies.
3. **Verify/download:** verify replicas, then download through the coordinator. The response is sent only after bytes
   from a node match the trusted SHA-256.
4. **Create version 2:** from the latest file's detail view, choose new contents and upload a version. Show its new
   file id, stable document id, version number, parent link, hash and `FILE_VERSION_CREATED` ledger record. The previous
   version remains separately listed and downloadable.
5. **Conflict policy:** submit a stale `expected_version` request based on version 1 after version 2 exists; the API
   returns HTTP 409 and identifies the latest version. The old record is not overwritten and no competing version is
   committed.
6. **Tenant sharing:** sign in as a second organization to show that the document is not visible by default. Grant
   read-only sharing from the owner account, demonstrate access to both versions, then revoke access and confirm both
   are hidden again. A shared reader cannot create versions or recover the file.
7. **Replica corruption/recovery:** in the test-only Attack Lab, enable malicious mode, corrupt one replica, verify the
   mismatch, and recover from a different copy whose downloaded bytes match the trusted hash.
8. **Automatic rejoin repair:** with enough healthy replicas available, stop a node, corrupt/remove its test replica or
   upload during downtime, then restart it. Show ledger catch-up and automatic replica reconciliation; a destination
   already matching the trusted hash is not rewritten.
9. **Invalid block:** submit an invalid proposal and show rejection with unchanged ledger heads.
10. **Events/limitations:** review organization-scoped activity. State clearly that voting is a coordinator-based
    signed 3-of-5 prototype, not Raft/PBFT or production BFT.

## Authenticated command-line checks

The smoke and benchmark scripts use a configured account. Set `TRUSTGRID_ORGANIZATION`, `TRUSTGRID_EMAIL`, and
`TRUSTGRID_PASSWORD`, or pass the `--organization`, `--email`, and `--password` options. If email/password are omitted,
the smoke script prompts interactively. Example:

```powershell
.\.venv\Scripts\python.exe scripts\smoke_test.py --mode local
```

The smoke script makes node failure/restart changes; do not run it against a deployment whose state must remain
untouched. A live smoke or browser walkthrough was not performed as part of the latest verification report.
