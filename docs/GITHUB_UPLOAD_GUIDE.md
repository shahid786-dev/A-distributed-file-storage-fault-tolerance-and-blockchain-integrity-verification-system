# GitHub Upload Guide

This guide explains how to upload BlockStore-5 to the GitHub repository:

`https://github.com/shahid786-dev/A-distributed-file-storage-fault-tolerance-and-blockchain-integrity-verification-system`

The commands below are for Windows PowerShell.

## 0. What was checked first

Before uploading:

1. The target GitHub repository was checked and found to be empty.
2. The project was located at `D:\CDC CEP\BlockStore-5\BlockStore-5`.
3. The local Git repository was initialized inside the project directory so the project files appear at the top level on GitHub.
4. `.gitignore` was checked to prevent generated files, secrets, runtime data, and the Python virtual environment from being uploaded.
5. The backend tests, frontend tests, frontend production build, and local end-to-end smoke test were run before publishing.

## 1. Install the required tools

Install these tools if they are not already installed:

- Git for Windows
- Python 3.11 or newer
- Node.js 18 or newer
- npm, installed with Node.js
- Docker Desktop, only if Docker deployment is required

Verify the installations:

```powershell
git --version
python --version
node --version
npm --version
```

## 2. Open the project directory

```powershell
Set-Location 'D:\CDC CEP\BlockStore-5\BlockStore-5'
```

Confirm that the project files are present:

```powershell
Get-ChildItem
```

The directory should contain `README.md`, `backend`, `frontend`, `storage_node`, `shared`, `scripts`, and `docker-compose.yml`.

## 3. Protect files that must not be uploaded

The project `.gitignore` excludes:

- `runtime/`, which contains local ledgers, uploaded files, logs, and process IDs
- `.env`, which may contain secrets and user credentials
- `.venv/`, the local Python virtual environment
- Python cache files and test caches
- `node_modules/` and the frontend build output

Never commit real passwords, API keys, private certificates, or production secrets. Use `.env.example` as the safe configuration template.

Check for accidentally tracked sensitive files before committing:

```powershell
git status --short --ignored
```

## 4. Initialize Git in the correct directory

If the project has not been initialized as a repository yet:

```powershell
git init -b main
```

If Git reports that a repository already exists, do not initialize it again. Check its location:

```powershell
git rev-parse --show-toplevel
```

The output must be:

`D:/CDC CEP/BlockStore-5/BlockStore-5`

If the output points to the parent directory, move into the project directory and initialize Git there. This keeps the uploaded project files at the root of the GitHub repository.

## 5. Configure Git identity

Set the name and email that should appear in the commit history. These values do not need to be the same as the GitHub login, but the email should be associated with the GitHub account if you want the commit linked to your profile.

```powershell
git config user.name 'Your Name'
git config user.email 'your-email@example.com'
```

Check the configuration:

```powershell
git config --get user.name
git config --get user.email
```

## 6. Add the GitHub remote

Add the target repository as `origin`:

```powershell
git remote add origin 'https://github.com/shahid786-dev/A-distributed-file-storage-fault-tolerance-and-blockchain-integrity-verification-system.git'
```

Verify it:

```powershell
git remote -v
```

If `origin` already exists and points to the wrong repository, update it instead:

```powershell
git remote set-url origin 'https://github.com/shahid786-dev/A-distributed-file-storage-fault-tolerance-and-blockchain-integrity-verification-system.git'
```

## 7. Stage the project files

```powershell
git add .
```

Review exactly what will be committed:

```powershell
git status

git diff --cached --stat
```

Look for mistakes such as `.env`, `.venv`, `runtime`, `node_modules`, database files, or passwords. If a sensitive file appears, stop and remove it from the staged area before continuing.

## 8. Create the first commit

```powershell
git commit -m 'Initial upload of BlockStore-5 project'
```

Confirm the commit exists:

```powershell
git log --oneline --decorate -3
```

## 9. Authenticate with GitHub

Push using HTTPS:

```powershell
git push -u origin main
```

GitHub no longer accepts an account password for Git operations over HTTPS. When prompted, use:

- Username: your GitHub username
- Password: a GitHub Personal Access Token with permission to push to the repository

Never place the token inside this guide, source code, `.env`, or a public command transcript.

A safer alternative is GitHub CLI:

```powershell
gh auth login
git push -u origin main
```

If SSH is already configured, the remote can instead use:

```powershell
git remote set-url origin 'git@github.com:shahid786-dev/A-distributed-file-storage-fault-tolerance-and-blockchain-integrity-verification-system.git'
git push -u origin main
```

## 10. Verify the upload

Check the remote branch:

```powershell
git ls-remote --heads origin
```

Open the repository in a browser:

`https://github.com/shahid786-dev/A-distributed-file-storage-fault-tolerance-and-blockchain-integrity-verification-system`

Confirm that:

- `README.md` is visible at the repository root.
- `backend`, `frontend`, `storage_node`, `shared`, `scripts`, and `docs` are visible.
- `.env`, `.venv`, `runtime`, and `node_modules` are not visible.
- The README links and screenshots open correctly.

## 11. Commands used to verify the project before upload

From the project directory:

```powershell
.\.venv\Scripts\python.exe -m pytest -q backend

Push-Location frontend
npm test
npm run build
Pop-Location

.\.venv\Scripts\python.exe scripts\smoke_test.py --mode local
```

The completed verification produced:

- 45 backend tests passed
- 6 frontend tests passed
- Vite production build passed
- Local end-to-end smoke test passed, including replication, version conflicts, tamper recovery, invalid-block rejection, node failure, node restart, automatic catch-up, and ledger agreement

## 12. Future updates

After changing the project:

```powershell
Set-Location 'D:\CDC CEP\BlockStore-5\BlockStore-5'
git status
git add .
git commit -m 'Describe the change'
git push
```

Before every push, review the staged diff:

```powershell
git diff --cached
```

Keep commit messages short and specific, for example:

- `Fix backend port override in smoke tests`
- `Improve replica recovery reporting`
- `Update setup documentation`

## 13. Common problems

### `src refspec main does not match any`

There is no commit yet. Create one first:

```powershell
git add .
git commit -m 'Initial upload of BlockStore-5 project'
```

### `remote origin already exists`

Inspect or replace the remote:

```powershell
git remote -v
git remote set-url origin 'https://github.com/shahid786-dev/A-distributed-file-storage-fault-tolerance-and-blockchain-integrity-verification-system.git'
```

### Authentication failed

Use a GitHub Personal Access Token or run `gh auth login`. Do not use the GitHub account password as the HTTPS password.

### Push rejected because the remote is not empty

First inspect the remote history. Do not overwrite it blindly. If the remote only contains an unwanted initial README and it is safe to replace, fetch and merge it before pushing:

```powershell
git fetch origin
git merge origin/main --allow-unrelated-histories
git push -u origin main
```

### A secret was committed accidentally

Immediately rotate the exposed secret. Removing the file in a later commit does not remove it from Git history. Rewrite history only after coordinating with anyone else using the repository.
