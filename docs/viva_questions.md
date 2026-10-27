# Viva preparation — 30 questions and answers

### Cloud and distributed computing
**1. What is cloud computing?**
On-demand access over a network to shared computing resources (servers, storage, services) that can be provisioned
quickly, paid for by use, and scaled up or down. BlockStore-5 runs locally but models a cloud storage service built
from several independent servers.

**2. What is distributed computing / a distributed system?**
Several independent computers (here: five node services) that cooperate over a network and appear to the user as one
system. They have no shared memory and fail independently, so they must communicate by messages — in our case HTTP.

**3. Why are the five nodes "independent" in your project?**
Each is a separate container/process with its own identity, port, storage volume, ledger file and memory. They
interact only through HTTP requests. Stopping one container does not affect the others.

**4. What does the coordinator do?**
It receives uploads, calculates the trusted hash, replicates to the nodes, checks hashes, runs health checks, collects
votes and commits blocks. It is a single point of failure, which we document as a limitation.

### Replication, availability, fault tolerance
**5. What is replication?**
Keeping several copies of the same data on different nodes. We keep five full copies of every file.

**6. What is availability?**
The fraction of time the service can answer requests. With five replicas, a file can still be read when up to four
nodes are down, as long as one verified copy is reachable.

**7. What is fault tolerance?**
The ability to keep working correctly when some components fail. We tolerate node crashes (reads continue; writes
and commits continue while ≥ 3 nodes are up) and one malicious node (its bad data and bad votes are outvoted/ignored).

**8. Fault tolerance vs backup?**
Fault tolerance keeps the service running during failures. A backup is a separate, versioned copy used to restore
after data is lost or wrongly changed. If a user deletes a file through the system, all replicas change — replication
is not a backup.

**9. How do you detect a node failure?**
The coordinator calls `GET /health` on every node every 2 seconds with a 1.5-second timeout. A refused connection,
timeout or HTTP error marks the node offline, logs an event and commits a `NODE_FAILURE` record.

**10. What happens when a node comes back?**
The health check sees it again, sends it the ledger blocks it missed (it validates each before appending), and a
`NODE_REJOINED` record is committed. Files it missed are re-copied with "Recover file".

**11. Why a write quorum of 3?**
3 is a majority of 5. Any two majorities overlap in at least one node, so two conflicting decisions cannot both get
a majority (in this simplified, one-proposal-at-a-time setting). It also tolerates 2 crashed nodes.

### Consistency
**12. What is consistency here?**
All nodes holding the same data: identical file bytes (checked by hash) and identical committed ledger (same head hash
and valid history). The ledger explorer shows each node as consistent, behind, diverged or invalid.

**13. Is the system strongly consistent?**
For the ledger, a block is committed only with a majority and appended in the same order everywhere, so honest online
nodes agree. Nodes that were offline are temporarily *behind* and catch up — eventual consistency for them.

### Hashing and SHA-256
**14. What is a hash function?**
A function that maps any input to a fixed-size value. A cryptographic hash is one-way and collision-resistant, and a
tiny change in input changes the output completely.

**15. Why SHA-256?**
It produces a 256-bit (64 hex character) digest, is standard, fast, available in every language, and no practical
collisions are known, so equal hashes mean equal content for our purposes.

**16. How is a replica's integrity verified?**
The coordinator downloads the replica and computes SHA-256 itself, then compares it with the trusted hash stored at
upload. It never relies on the hash the node reports — a malicious node in our demo lies about it.

**17. Can hashing tell you who tampered?**
No. It only tells you the content differs. A mismatch could be an attack, disk corruption or a bug.

### Blockchain
**18. What is in a block?**
Index, timestamp, previous block hash, a list of transactions, proposer, and the block's own SHA-256 hash.

**19. What is the genesis block?**
The first block (index 0). It has fixed contents so every node creates exactly the same one with the same hash; all
other blocks chain back to it.

**20. What does the previous hash do?**
It links each block to the one before. Changing an old block changes its hash, which no longer matches the
`previous_hash` stored in the next block, so the tampering is detected.

**21. Does the blockchain make data impossible to change?**
No. Someone who controls a copy can edit it and even recompute hashes. It is detectable because the other copies and
the majority disagree. We demonstrate this with "Tamper with local ledger".

**22. Why not store the file in the blockchain?**
Blocks are copied to every node and kept forever; storing files would make the ledger huge. We store metadata and the
hash (integrity evidence) only — transactions over 2 KB or with a content field are rejected.

**23. Why no mining or cryptocurrency?**
Mining (proof of work) is for open networks where anyone can join. We have five known, registered nodes, so voting is
enough and much cheaper.

### Consensus, voting and malicious nodes
**24. What is consensus?**
Agreement among distributed nodes on a single value — here, the next ledger block.

**25. Explain your voting protocol.**
The coordinator proposes a block; all five nodes validate it against their own copy and return signed accept/reject
votes; the coordinator counts valid, non-duplicate votes from registered nodes; with ≥ 3 accepts it sends the block to
all nodes, which validate it again and append it.

**26. How do you stop fake or duplicate votes?**
Each vote carries an HMAC-SHA256 tag over proposal id, node id, block hash and decision, made with that node's secret.
The coordinator checks it against the registered secret, checks the block hash, and counts only the first vote per
node.

**27. What does the malicious node do in the demo?**
Two separate attacks. (A) It changes its stored copy of a file and lies about the hash — detected by re-hashing,
4 honest copies remain, file repaired. (B) It proposes an invalid block (wrong previous hash, bad block hash, or
re-registering a file with a new hash) — it votes yes, the four honest nodes reject, so 1/5 < 3 and nothing changes.

**28. Is this Byzantine fault tolerant?**
No. Proper BFT (e.g. PBFT) needs n ≥ 3f + 1 nodes, several message rounds, no trusted coordinator and handling of
equivocation and view changes. Ours shows the honest-majority principle with one faulty node under controlled
conditions.

### Limitations
**29. What are the single points of failure?**
The coordinator (backend) and its SQLite database. Also, all nodes run on one machine in the demo.

**30. How would you improve it?**
Replicate the coordinator or use Raft/PBFT among the nodes; public-key signatures for votes; authentication and TLS;
encryption at rest; erasure coding instead of 5 full copies; automatic re-replication; deploy nodes on different
machines or cloud regions; versioned backups.
