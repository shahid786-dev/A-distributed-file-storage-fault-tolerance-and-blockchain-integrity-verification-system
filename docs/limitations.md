# Limitations and simplifications

BlockStore-5 is a small educational prototype. These limits are deliberate and should be stated in the viva.

## Architecture
1. **The coordinator is a single point of failure.** If the backend stops, nobody can upload, download or vote, even
   though all five nodes and their data are fine. A real system would replicate the coordinator or remove it
   (peer-to-peer consensus such as Raft/PBFT).
2. **The coordinator is trusted.** It computes the trusted hash, collects votes and distributes commits. A malicious
   coordinator could lie. Nodes re-validate every block before appending, which limits but does not remove this.
3. **One computer.** All five nodes run on one machine and one disk. This demonstrates the idea of independent
   failure, not geographic fault tolerance, real network latency or scalability.

## Consensus
4. **Simplified majority voting, not BFT.** Coordinator-based 3-of-5 voting with signed votes. It is not PBFT, Raft or
   any formally proven protocol, and does not guarantee safety under network partitions, coordinator failure,
   equivocation (a node sending different votes to different parties), or multiple competing proposals.
5. **One proposal at a time** (a lock in the coordinator). There is no leader election, no view change, no handling of
   concurrent proposers.
6. **Fault assumption:** at most one faulty or malicious node at a time and at least three honest nodes online.
7. **Votes use HMAC with secrets the coordinator also knows.** That proves to the coordinator that a vote came from a
   registered node, but the nodes cannot verify each other's votes. Public-key signatures (e.g. Ed25519) would allow
   that.

## Integrity and blockchain
8. **Hash linking makes tampering detectable, not impossible.** Someone who controls a ledger copy can rewrite it.
   It is detected only because the other copies and the majority disagree.
9. **Hashing detects a change but does not identify who made it.** A mismatching replica may be malicious tampering,
   a disk error or a bug. The transaction type `MALICIOUS_ACTIVITY_DETECTED` means "inconsistent replica found".
10. **Trust anchor assumption.** The original upload and its metadata are assumed legitimate. Organization login,
    roles, and document access checks are implemented, but the SQLite file and coordinator remain trusted.
11. **No encryption at rest.** File bytes are plaintext on node disks and service traffic is not protected by TLS in the
    supplied local/Compose setup. Browser-facing API reads require a bearer session; node data endpoints require the
    coordinator control token.

## Storage
12. **Full replication on every node** (5× storage). Erasure coding would use less space.
13. **Replication is not a backup.** Earlier document versions are immutable and addressable, but share the same
    coordinator metadata and five-node failure domain. There is no independent/offline backup or point-in-time restore
    after all copies or trusted metadata are lost.
14. **Rejoin repair is conditional.** Startup/rejoin repair only proceeds when another node can supply bytes matching
    the coordinator's trusted hash. Repair can succeed without a quorum-backed recovery ledger record; that limitation
    is logged, and must not be described as a ledger commit.
15. **Small files only** (10 MB limit); whole files are held in memory during transfer.

## Security of the prototype
16. Initial organization accounts must be explicitly configured with `TRUSTGRID_DEMO_USERS`; passwords are stored as
    salted PBKDF2 hashes and sessions expire, but there is no MFA, rate limiting, TLS setup, or production identity
    provider. Demo node-signing secrets and the control token have development defaults in Compose; replace them via
    `.env`. Simulation endpoints are limited to predefined actions (no shell or Docker control), but should not exist
    in a production system.

## Fault tolerance vs backup
Fault tolerance keeps the service working while some components fail (here: up to 2 of 5 nodes for writes, provided
3 remain for a quorum; verified reads may work with fewer). A backup is an independent, usually offline copy used to
restore data after it has been lost or wrongly changed. BlockStore-5 demonstrates replication and immutable logical
versions, not independent backup/restore.
