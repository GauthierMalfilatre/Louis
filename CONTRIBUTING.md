# Contributing

## Branches

```
main              stable. only dev or hotfix/* may merge here.
 ^
dev               where day-to-day work lands. branch from here.
 ^
feat/ fix/ chore/ one branch per issue.
```

Branch from `dev` and name it after what it does:

| Prefix   | For                                  | Example                  |
| -------- | ------------------------------------ | ------------------------ |
| `feat/`  | a new capability                     | `feat/password-reset`    |
| `fix/`   | a bug in `dev`                       | `fix/login-500`          |
| `chore/` | tooling, CI, docs, dependencies      | `chore/bump-vite`        |
| `hotfix/`| a bug in **released** code on `main` | `hotfix/expired-token`   |

```bash
git switch dev
git pull
git switch -c feat/password-reset
```

## Commits

`verb: lowercase sentence.` — ending with a period, matching the existing history:

```
add: add basic auth system.
update: update feature template.
fix: fix the user lookup that ignored the profile embed.
```

Verbs in use: `add`, `update`, `fix`, `remove`, `refactor`. This is deliberately
not Conventional Commits — don't write `feat(auth):`.

## Pull requests

1. Push your branch and open a PR **into `dev`**. The template fills itself in.
2. Put `Closes #12` in the description so the issue closes when it merges.
3. CI runs. Wait for those to be green.
4. Get one teammate to approve. Don't merge your own PR unreviewed.
5. Squash or merge — either is fine, but don't force-push a branch someone is
   already reviewing.

The repo doesn't enforce any of this: GitHub will show the merge button even
with red CI and no review. It is a team rule, so hold each other to it.

## Hotfixes

When something is broken on `main` and cannot wait for `dev`:

```bash
git switch main
git pull
git switch -c hotfix/expired-token
# fix, commit, push
```

Open the PR **into `main`**. The `guard-main` CI job allows this because the
branch is `hotfix/*`; a PR into `main` from anything else turns that check red.
A red `guard-main` means retarget the PR at `dev`, not merge anyway.

**Then merge `main` back into `dev` immediately:**

```bash
git switch dev
git pull
git merge main
git push
```

Skip this and the fix exists only on `main`. The next `dev` → `main` merge will
either revert it or hand you a conflict in the worst possible week.

## Repo setup (one-time)

1. Create `dev` if it does not exist:
   ```bash
   git switch -c dev && git push -u origin dev
   ```
2. Settings → Labels: make sure `type:bug` and `type:feature` exist, or the
   issue templates will silently fail to apply them.

`main` stays the default branch. `dev` is where PRs land day to day.
