"""Unit tests for the shared educational blockchain (no network needed)."""
import copy

from shared.blockcore import (GENESIS_HASH, compute_block_hash, genesis_block, make_block, utc_now,
                              validate_chain, validate_new_block, validate_transaction)

SHA = "a" * 64


def upload_tx(file_id="f" * 32, sha=SHA):
    return {"type": "FILE_UPLOADED", "file_id": file_id, "file_name": "a.txt", "size": 3,
            "sha256": sha, "timestamp": utc_now()}


def chain_with_one_upload():
    g = genesis_block()
    return [g, make_block(1, g["hash"], [upload_tx()], "coordinator")]


def test_genesis_is_identical_everywhere():
    assert genesis_block() == genesis_block()
    assert genesis_block()["hash"] == GENESIS_HASH


def test_block_hash_is_deterministic():
    b = make_block(1, GENESIS_HASH, [upload_tx()], "coordinator", timestamp="2026-01-01T00:00:00.000Z")
    assert compute_block_hash(copy.deepcopy(b)) == b["hash"]


def test_valid_block_is_accepted():
    g = genesis_block()
    assert validate_new_block(make_block(1, g["hash"], [upload_tx()], "coordinator"), [g]) is None


def test_block_sees_earlier_transactions_in_the_same_block():
    g = genesis_block()
    tx1 = upload_tx(file_id="a" * 32, sha="a" * 64)
    tx2 = upload_tx(file_id="b" * 32, sha="b" * 64)
    block = make_block(1, g["hash"], [tx1, tx2], "coordinator")
    assert validate_new_block(block, [g]) is None

    dup = upload_tx(file_id="a" * 32, sha="c" * 64)
    bad = make_block(1, g["hash"], [tx1, dup], "coordinator")
    assert "already committed" in validate_new_block(bad, [g])

    replicated = {"type": "FILE_REPLICATED", "file_id": "a" * 32, "sha256": "a" * 64,
                  "nodes_ok": ["node1"], "nodes_failed": [], "timestamp": utc_now()}
    block = make_block(1, g["hash"], [tx1, replicated], "coordinator")
    assert validate_new_block(block, [g]) is None

    replicated["sha256"] = "c" * 64
    bad = make_block(1, g["hash"], [tx1, replicated], "coordinator")
    assert "trusted hash" in validate_new_block(bad, [g])


def test_document_version_must_extend_the_committed_latest_version():
    g = genesis_block()
    first = upload_tx(file_id="a" * 32, sha="a" * 64)
    first.update({"document_id": "a" * 32, "version_number": 1})
    version = {"type": "FILE_VERSION_CREATED", "file_id": "b" * 32, "document_id": "a" * 32,
               "version_number": 2, "previous_file_id": "a" * 32, "file_name": "a.txt",
               "size": 4, "sha256": "b" * 64, "timestamp": utc_now()}
    first_block = make_block(1, g["hash"], [first], "coordinator")
    assert validate_new_block(first_block, [g]) is None
    assert validate_transaction(version, [g, first_block]) is None

    skipped = {**version, "version_number": 3}
    assert "increment the parent version" in validate_transaction(skipped, [g, first_block])
    wrong_document = {**version, "document_id": "c" * 32}
    assert "does not match the parent" in validate_transaction(wrong_document, [g, first_block])
    malformed_id = {**version, "file_id": "not-a-file-id"}
    assert "32-character lowercase hex" in validate_transaction(malformed_id, [g, first_block])


def test_document_versions_can_depend_on_an_earlier_transaction_in_the_same_block():
    g = genesis_block()
    first = upload_tx(file_id="a" * 32, sha="a" * 64)
    first.update({"document_id": "a" * 32, "version_number": 1})
    second = {"type": "FILE_VERSION_CREATED", "file_id": "b" * 32, "document_id": "a" * 32,
              "version_number": 2, "previous_file_id": "a" * 32, "file_name": "a.txt",
              "size": 4, "sha256": "b" * 64, "timestamp": utc_now()}
    block = make_block(1, g["hash"], [first, second], "coordinator")
    assert validate_new_block(block, [g]) is None

    competing = {**second, "file_id": "c" * 32, "sha256": "c" * 64}
    bad = make_block(1, g["hash"], [first, second, competing], "coordinator")
    assert "previous_file_id must reference the latest" in validate_new_block(bad, [g])


def test_block_with_invalid_hash_is_rejected():            # requirement 10
    g = genesis_block()
    b = make_block(1, g["hash"], [upload_tx()], "coordinator")
    b["transactions"][0]["size"] = 999                        # content changed after hashing
    assert "hash" in validate_new_block(b, [g])


def test_block_with_wrong_previous_hash_is_rejected():     # requirement 11
    g = genesis_block()
    b = make_block(1, "b" * 64, [upload_tx()], "coordinator")
    assert "previous_hash" in validate_new_block(b, [g])


def test_non_sequential_index_is_rejected():
    g = genesis_block()
    assert "sequential" in validate_new_block(make_block(5, g["hash"], [upload_tx()], "coordinator"), [g])


def test_unregistered_proposer_is_rejected():
    g = genesis_block()
    assert "registered" in validate_new_block(make_block(1, g["hash"], [upload_tx()], "node9"), [g])


def test_overwriting_a_trusted_hash_is_rejected():
    chain = chain_with_one_upload()
    problem = validate_transaction(upload_tx(sha="e" * 64), chain)
    assert problem and "cannot be overwritten" in problem


def test_unknown_type_and_file_contents_are_rejected():
    assert "unknown" in validate_transaction({"type": "MINT", "timestamp": utc_now()}, [genesis_block()])
    tx = upload_tx()
    tx["content"] = "the whole file"
    assert "contents" in validate_transaction(tx, [genesis_block()])


def test_integrity_record_must_use_committed_hash():
    chain = chain_with_one_upload()
    tx = {"type": "INTEGRITY_CHECKED", "file_id": "f" * 32, "sha256": "c" * 64, "matching": [],
          "mismatching": [], "unavailable": [], "timestamp": utc_now()}
    assert "trusted hash" in validate_transaction(tx, chain)


def test_validate_chain_detects_edited_history():
    chain = chain_with_one_upload()
    chain.append(make_block(2, chain[-1]["hash"], [{"type": "NODE_REJOINED", "node_id": "node2",
                                                    "timestamp": utc_now()}], "coordinator"))
    assert validate_chain(chain)["valid"]
    chain[1]["transactions"][0]["sha256"] = "f" * 64           # attacker edits block 1 in place
    result = validate_chain(chain)
    assert not result["valid"]
    assert result["errors"][0]["index"] == 1


def test_validate_chain_rejects_semantically_invalid_rehashed_history():
    g = genesis_block()
    first = upload_tx(file_id="a" * 32, sha="a" * 64)
    duplicate = upload_tx(file_id="a" * 32, sha="c" * 64)
    block = make_block(1, g["hash"], [first, duplicate], "coordinator")
    result = validate_chain([g, block])
    assert not result["valid"]
    assert result["errors"][0]["index"] == 1
    assert "already committed" in result["errors"][0]["problem"]


def test_validate_chain_rejects_file_transaction_without_prior_upload():
    g = genesis_block()
    replicated = {"type": "FILE_REPLICATED", "file_id": "e" * 32, "sha256": SHA,
                  "nodes_ok": ["node1"], "nodes_failed": [], "timestamp": utc_now()}
    chain = [g, make_block(1, g["hash"], [replicated], "coordinator")]
    result = validate_chain(chain)
    assert not result["valid"]
    assert "no committed FILE_UPLOADED" in result["errors"][0]["problem"]
