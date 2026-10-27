# Verification report

## Scope

This report records checks executed against the current workspace after the transaction-validation, authentication,
automatic replica-repair, and document-versioning changes. It is not a certification against the CS-485 rubric; that
manual was not available in the supplied workspace.

## Automated results

| Suite / command | Result | Coverage / note |
|---|---:|---|
| `.\.venv\Scripts\python.exe -m pytest -q backend\tests\test_blockchain_unit.py backend\tests\test_database_unit.py` | **17 passed** (0.18 s) | Same-block validation, full-chain semantic validation, version parent/sequence checks, and migration of a pre-version files table. |
| `.\.venv\Scripts\python.exe -m pytest -q backend` | **45 passed** (61.18 s) | Full unit and live-cluster integration suite, including auth/tenant access, sharing, replica rejoin repair, immutable version creation, and stale-parent HTTP 409 behavior. |
| `npm test` (from `frontend`) | **6 passed** | API error handling and auth header/login/logout behavior when browser session storage is denied. |
| `npm run build` (from `frontend`) | **Passed** | Vite 6.4.5 production bundle. |
| Python syntax checks | **No syntax errors** | Checked modified service, API, database, blockchain, and smoke/benchmark Python files. |
| `scripts/smoke_test.py --help`, `scripts/benchmark.py --help` | **Passed** | CLI exposes organization/email/password options and environment-backed credentials. |

The first full-suite run after versioning found one assertion coupled to the old wording for a file with no prior upload.
The validation behavior was correct; the error text was extended to mention both initial uploads and version records while
retaining the prior `FILE_UPLOADED` wording. The final complete suite above passed.

## Not run

- The authenticated smoke test was not run against a live configured Docker/local demo stack.
- No post-change browser walkthrough or persistent-volume restart test was performed.
- No claim is made about all course requirements, production security, or full project completion.

See [DEMO_GUIDE.md](./DEMO_GUIDE.md) for a repeatable manual walkthrough and [LAB_MAPPING.md](./LAB_MAPPING.md) for
the boundary between repository evidence and unavailable manual requirements.
