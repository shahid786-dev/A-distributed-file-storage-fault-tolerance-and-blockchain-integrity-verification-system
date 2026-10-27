"""Pydantic request models. Node ids are restricted to the five registered identities,
so the frontend cannot invent a node."""
from typing import Literal

from pydantic import BaseModel, Field

NodeId = Literal["node1", "node2", "node3", "node4", "node5"]
FileId = str  # validated with the pattern below where it is used
FILE_ID_PATTERN = r"^[0-9a-f]{32}$"


class NodeRequest(BaseModel):
    node_id: NodeId


class MaliciousRequest(BaseModel):
    node_id: NodeId = "node3"
    enabled: bool


class CorruptRequest(BaseModel):
    node_id: NodeId = "node3"
    file_id: str = Field(pattern=FILE_ID_PATTERN)
    confirm: bool = Field(description="Must be true: this is a destructive test operation")


class InvalidBlockRequest(BaseModel):
    node_id: NodeId = "node3"
    attack: Literal["wrong_previous_hash", "bad_block_hash", "overwrite_trusted_hash"] = "wrong_previous_hash"
    file_id: str | None = Field(default=None, pattern=FILE_ID_PATTERN)


class TamperLedgerRequest(BaseModel):
    node_id: NodeId = "node3"
    confirm: bool


class ProposeRequest(BaseModel):
    """Manually propose one transaction (it is still validated and voted on by the nodes)."""
    transaction: dict


class LoginRequest(BaseModel):
    organization: Literal["manufacturer", "logistics", "inspection", "distributor"]
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=256)


class ShareRequest(BaseModel):
    organization: Literal["manufacturer", "logistics", "inspection", "distributor"]
    permission: Literal["read"] = "read"
