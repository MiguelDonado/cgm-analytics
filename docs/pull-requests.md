# Pull requests

A **pull request (PR)** is a GitHub page that asks to merge one branch (e.g.
`ci/unit-tests`) into another (usually `main`). The merge itself is the same as a
local `git merge`; the PR adds a place to check the change first:

- **CI runs on the branch** and shows ✓ or ✗ on the PR before anything reaches `main`.
- **Files changed** shows the full diff, and reviewers can comment on single lines.
- **A record** stays in the repo: description, commits, comments and CI results.

A PR doesn't store a copy of the code: it **points at the branch**. While it's
open, every push to the branch updates it and reruns CI. Once merged or closed,
it's frozen, and later pushes to the branch don't change it.

## The full cycle

### 1. Create a branch from an up-to-date `main`

```bash
git switch main
git pull                       # start from the latest main
git switch -c ci/unit-tests    # new branch, and switch to it
```

### 2. Commit and push

```bash
git add <files>
git commit -m "Add unit tests and run them in CI"
git push -u origin ci/unit-tests   # -u: later, a plain `git push` is enough
```

### 3. Open the PR

`git push` prints a link (`.../pull/new/ci/unit-tests`). Open it, write a title
and description, and click **Create pull request**. Or, in the repo on GitHub, go
to **Pull requests → New pull request**, with `base: main` and `compare: ci/unit-tests`.

### 4. Check CI, and push fixes if needed

The **CI / test** check appears at the bottom of the PR. Click **Details** to
see each step's output. If it fails or you want another change, keep committing
on the same branch:

```bash
git add <files>
git commit -m "Fix ..."
git push                       # the open PR updates by itself, CI runs again
```

### 5. Merge on GitHub

Click **Merge pull request** once CI is green, then **Delete branch**. That
deletes the branch on GitHub only. To do this automatically, tick
**Settings → General → Pull Requests → Automatically delete head branches**.

### 6. Update the laptop

The merge happened on GitHub, so the local `main` doesn't have it yet:

```bash
git switch main
git pull                       # bring the merge into the local main
git branch -d ci/unit-tests    # delete the local branch
git fetch --prune              # forget remote branches deleted on GitHub
```

`git branch -d` refuses if the branch has commits that never reached `main`.
Don't force it with `-D`: check them with `git log main..ci/unit-tests` first.

## Changes after the PR was merged

New commits on a merged branch go nowhere. Start a new branch from the updated
`main` and open a new PR. With uncommitted changes, stash them first, because
git won't switch branches if they clash with files that differ between branches:

```bash
git stash                      # set the changes aside
git switch main
git pull
git switch -c fix/something
git stash pop                  # bring the changes back
git add -A && git commit -m "..."
git push -u origin fix/something
```

## PR vs local merge

Merging locally gives the same result on `main`, without the check before merging:

```bash
git switch main
git merge ci/unit-tests
git push origin main
```

CI still runs (the workflow triggers on push to `main`), but only once the code
is already there; a failure is fixed with another commit. PRs are worth it for
**branch protection** (`main` only accepts PRs with passing CI) and to keep a
visible history of each change.