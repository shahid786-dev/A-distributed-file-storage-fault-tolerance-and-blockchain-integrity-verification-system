"""
BlockStore-5 storage node - one independent HTTP service.

Five copies of this service run side by side (node1..node5), each with its own
identity, port, data directory and ledger copy. The coordinator backend talks to
them only through the HTTP endpoints below.

Run one node locally:
    NODE_ID=node1 NODE_DATA_DIR=./runtime/node1 uvicorn storage_node.node_app.main:app --port 8001
"""
from fastapi import Body, Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from shared.blockcore import validate_chain

from . import consensus, health, ledger, storage
from .config import CONTROL_TOKEN, MAX_FILE_BYTES, NODE_ID

app = FastAPI(title=f"BlockStore-5 storage node ({NODE_ID})", version="1.0")


# ---------------------------------------------------------------------------
# Simulated failure: while active, the node answers every request with 503,
# exactly as the coordinator would see a crashed or unreachable service.
# Only /simulation/recover still works so the test can be reversed.
# ---------------------------------------------------------------------------
@app.middleware("http")
async def simulated_failure_gate(request: Request, call_next):
    if health.get("simulated_failure") and request.url.path != "/simulation/recover":
        return JSONResponse(status_code=503,
                            content={"detail": f"{NODE_ID} is in simulated failure mode"})
    return await call_next(request)


def require_control_token(x_control_token: str = Header(default="")):
    """Write and control endpoints are only for the coordinator, which knows the token."""
    if x_control_token != CONTROL_TOKEN:
        raise HTTPException(status_code=401, detail="missing or wrong X-Control-Token")


def check_file_id(file_id: str):
    if not storage.valid_file_id(file_id):
        raise HTTPException(status_code=400, detail="file_id must be 32 lowercase hex characters")


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------
@app.get("/health")
def health_check():
    chain = ledger.get_chain()
    return {
        "node_id": NODE_ID,
        "status": "online",
        "file_count": len(list(storage.FILES_DIR.glob("*.bin"))),
        "ledger_height": len(chain),
        "ledger_head_hash": chain[-1]["hash"],
        "malicious_simulation": health.get("malicious"),
        "uptime_seconds": health.uptime_seconds(),
    }


# ---------------------------------------------------------------------------
# File storage
# ---------------------------------------------------------------------------
@app.put("/files/{file_id}", dependencies=[Depends(require_control_token)])
async def store_file(file_id: str, request: Request):
    check_file_id(file_id)
    data = await request.body()
    if len(data) > MAX_FILE_BYTES:
        raise HTTPException(status_code=413, detail="file too large")
    meta = storage.save(file_id, data)
    # Return the hash of what we actually wrote so the coordinator can compare it
    return {"node_id": NODE_ID, "file_id": file_id, "size": meta["size"], "sha256": meta["sha256_at_store"]}


@app.get("/files", dependencies=[Depends(require_control_token)])
def list_files():
    return {"node_id": NODE_ID, "files": storage.list_files()}


@app.get("/files/{file_id}", dependencies=[Depends(require_control_token)])
def get_file(file_id: str):
    check_file_id(file_id)
    if not storage.exists(file_id):
        raise HTTPException(status_code=404, detail=f"{NODE_ID} has no copy of {file_id}")
    return Response(content=storage.read(file_id), media_type="application/octet-stream",
                    headers={"X-Node-Id": NODE_ID})


@app.get("/files/{file_id}/hash", dependencies=[Depends(require_control_token)])
def get_file_hash(file_id: str):
    """The hash this node CLAIMS for its copy. The coordinator never trusts this alone -
    it downloads the bytes and recalculates the hash itself."""
    check_file_id(file_id)
    if not storage.exists(file_id):
        raise HTTPException(status_code=404, detail="not found")
    if health.get("malicious"):
        # A dishonest node lies: it reports the hash it had when the file was stored.
        reported = storage.meta(file_id)["sha256_at_store"]
    else:
        reported = storage.current_hash(file_id)
    return {"node_id": NODE_ID, "file_id": file_id, "sha256": reported}


@app.delete("/files/{file_id}", dependencies=[Depends(require_control_token)])
def delete_file(file_id: str):
    check_file_id(file_id)
    return {"node_id": NODE_ID, "deleted": storage.delete(file_id)}


# ---------------------------------------------------------------------------
# Ledger and voting
# ---------------------------------------------------------------------------
@app.get("/ledger", dependencies=[Depends(require_control_token)])
def get_ledger():
    chain = ledger.get_chain()
    return {"node_id": NODE_ID, "chain": chain, "validation": validate_chain(chain)}


class VoteRequest(BaseModel):
    proposal_id: str = Field(min_length=8, max_length=64)
    block: dict


@app.post("/consensus/vote", dependencies=[Depends(require_control_token)])
def vote(req: VoteRequest):
    return consensus.vote(req.proposal_id, req.block)


class CommitRequest(BaseModel):
    proposal_id: str
    block: dict
    accept_votes: int = Field(ge=0, le=5)


@app.post("/consensus/commit", dependencies=[Depends(require_control_token)])
def commit(req: CommitRequest):
    if req.accept_votes < 3:
        raise HTTPException(status_code=400, detail="commit refused: fewer than 3 accept votes")
    problem = ledger.append(req.block)
    if problem:
        raise HTTPException(status_code=409, detail=f"{NODE_ID} refused block: {problem}")
    return {"node_id": NODE_ID, "committed_index": req.block["index"], "head_hash": req.block["hash"]}


@app.post("/ledger/sync", dependencies=[Depends(require_control_token)])
def sync_ledger(blocks: list = Body(..., embed=True)):
    result = ledger.sync(blocks)
    result["ledger_height"] = len(ledger.get_chain())
    return result


@app.post("/ledger/replace", dependencies=[Depends(require_control_token)])
def replace_ledger(chain: list = Body(..., embed=True)):
    problem = ledger.replace(chain)
    if problem:
        raise HTTPException(status_code=409, detail=problem)
    return {"node_id": NODE_ID, "ledger_height": len(chain)}


# ---------------------------------------------------------------------------
# Simulation controls (TEST ONLY). Predefined actions, no shell access.
# ---------------------------------------------------------------------------
@app.post("/simulation/fail", dependencies=[Depends(require_control_token)])
def simulate_failure():
    health.set_flag("simulated_failure", True)
    return {"node_id": NODE_ID, "simulated_failure": True}


@app.post("/simulation/recover", dependencies=[Depends(require_control_token)])
def simulate_recover():
    health.set_flag("simulated_failure", False)
    return {"node_id": NODE_ID, "simulated_failure": False}


class MaliciousRequest(BaseModel):
    enabled: bool


@app.post("/simulation/malicious", dependencies=[Depends(require_control_token)])
def set_malicious(req: MaliciousRequest):
    health.set_flag("malicious", req.enabled)
    return {"node_id": NODE_ID, "malicious_simulation": req.enabled}


def require_malicious():
    if not health.get("malicious"):
        raise HTTPException(status_code=403,
                            detail=f"{NODE_ID} is not in malicious-simulation mode; enable it first")


@app.post("/simulation/corrupt/{file_id}",
          dependencies=[Depends(require_control_token), Depends(require_malicious)])
def corrupt_replica(file_id: str):
    check_file_id(file_id)
    if not storage.exists(file_id):
        raise HTTPException(status_code=404, detail=f"{NODE_ID} has no copy of {file_id}")
    return {"node_id": NODE_ID, "file_id": file_id, **storage.corrupt(file_id)}


class InvalidBlockRequest(BaseModel):
    attack: str
    file_id: str | None = None


@app.post("/simulation/propose-invalid",
          dependencies=[Depends(require_control_token), Depends(require_malicious)])
def propose_invalid(req: InvalidBlockRequest):
    try:
        block = consensus.build_invalid_block(req.attack, req.file_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"node_id": NODE_ID, "attack": req.attack,
            "description": consensus.ATTACKS[req.attack], "block": block}


@app.post("/simulation/tamper-ledger",
          dependencies=[Depends(require_control_token), Depends(require_malicious)])
def tamper_ledger():
    return {"node_id": NODE_ID, **ledger.tamper_past_block()}
