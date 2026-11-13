# AllStore.am: CI restructuring plan

Written 2026-11-13. Baseline: `allstore-ci.md` (current state). This plan changes the *shape* of CI
and the *testing rules*. It does not cover deploy, security scans or prod-image builds; those stay
in the backlog (see §9).

---

## 1. Goals

1. CI is split into three stages with one job per concern: **code-quality**, **unit-tests**, **e2e-tests**.
2. Back and front are always separate jobs, so a red tick says which side broke.
3. Tests are trustworthy: **100% coverage** is the acceptance criterion, unit tests run in
   **random order**, and the unit-test tree is a **mirror of the source tree**.
4. **mutmut** (mutation testing) is available locally now; CI integration comes later.
5. Adding a linter later must be a one-line change, not a workflow rewrite.

---

## 2. Target pipeline

```
                 ┌─ lint-back ──┐
                 ├─ lint-front ─┤
 PR / push main ─┼─ unit-back ──┼──► gate
                 ├─ unit-front ─┤
                 └─ e2e ────────┘
```

All five jobs start at the same time (no `needs:` between them). Total wall time is the slowest job
(e2e, about 5 min). Only `gate` waits.

| Stage | Job | What it proves |
| --- | --- | --- |
| code-quality | `lint-back` | style, types, generated files are fresh |
| code-quality | `lint-front` | style, types |
| unit-tests | `unit-back` | logic, 100% coverage, random order |
| unit-tests | `unit-front` | logic, 100% coverage, random order |
| e2e-tests | `e2e` | the whole product, driven like a human in a browser |
| (meta) | `gate` | single required check for branch protection |

Design decisions:

- **One workflow file (`ci.yml`)** with these jobs instead of four. The three stages are a grouping
  for humans (job names and the PR checks list), not an execution order.
- **Fully parallel.** No `needs:` between lint, unit and e2e jobs, so feedback arrives as fast as
  possible and a green run takes only as long as the slowest job. Trade-off: when lint fails in
  30 seconds, e2e still runs to the end and spends runner minutes. Accepted because e2e is only
  4-5 minutes. If runner minutes become a cost problem, the cheapest fix is `needs: [lint-back, lint-front]`
  on `e2e` alone (lint takes about a minute); the unit jobs stay parallel with it.
- Parallel jobs count against the concurrent-job limit (20 on the free plan); five is well within it.
- **Drop path filters.** Lanes are cheap with caching, and every PR then runs everything. This also
  removes the "required check pending forever" problem on docs-only PRs. `search-ci` folds in
  as `lint-search` / `unit-search` with the same rules (see §9, open question 5).
- **`gate` job** (`if: always()`, `needs:` every job, fails if any needed job failed or was cancelled).
  Branch protection requires only `gate`.
- **CI calls Makefile targets, not raw commands.** `make lint-back`, `make lint-front`,
  `make unit-back`, `make unit-front`, `make e2e`. Adding a linter = edit one Makefile target
  (and the same target is what pre-commit and developers run locally). The workflow never changes.
- Keep: pinned action versions, `workflow_dispatch`, `concurrency` (cancel superseded PR runs, never
  cancel `main`), `timeout-minutes` on every job, dependency caches (`setup-node cache: npm`,
  `setup-uv enable-cache`).

---

## 3. Stage 1: code-quality (linters, extensible)

### `lint-back` (`make lint-back`)

```
ruff check .
ruff format --check .
mypy                                   strict
./scripts/gen-api-types.sh && git diff --exit-code frontend/src/lib/api-types.ts
tests-tree check                       see §5.3 (mirror enforcement)
```

### `lint-front` (`make lint-front`)

```
npm run lint            eslint
npm run format:check    prettier
npm run typecheck       next typegen && tsc --noEmit
tests-tree check        see §5.3
```

Notes:

- The generated-types check lives in `lint-back` because it is a "generated file is fresh" check,
  not a test. It needs the app importable, not a database.
- "Mutable" is literal: each lint target is an ordered list of commands in the Makefile. A future
  linter (bandit, vulture, knip, stylelint, ...) is added there. Each new linter gets its own
  line in the step log so a failure is identifiable.
- `pre-commit run --all-files` is **not** a separate lane. Pre-commit hooks should call the same
  Makefile pieces, so there is one definition of "lint".

---

## 4. Stage 2: unit-tests

### `unit-back` (`make unit-back`)

Services: postgres (`pgvector/pgvector:pg17`) and redis (`redis:8-alpine`), as today; see open
question 1 about whether pure unit tests should need them at all.

```
uv sync --frozen
alembic upgrade head
pytest tests/unit --cov --cov-branch --cov-report=term-missing --cov-report=xml   # random order, fail-under=100
```

### `unit-front` (`make unit-front`)

```
npm ci
vitest run --coverage --sequence.shuffle      # thresholds: 100
```

---

## 5. Testing rules (acceptance criteria)

### 5.1 Coverage: 100%

- **Scope changes from "changed lines ≥ 80%" to "whole project = 100%".** `diff-cover` becomes redundant
  and is removed once the threshold is live (this also removes the need for `fetch-depth: 0`).
- **Backend:** in `backend/pyproject.toml`
  - `[tool.coverage.run]`: `branch = true`; keep `concurrency = ["greenlet", "thread"]`.
  - `[tool.coverage.report]`: `fail_under = 100`, `show_missing = true`, `skip_covered = true`.
  - The current `omit = ["app/main.py"]` must be justified or removed. A 100% gate with silent
    omissions is not 100%.
- **Frontend:** `vitest.config.ts` → `coverage: { provider: "v8", thresholds: { lines: 100, branches: 100, functions: 100, statements: 100 } }`
  with `include: ["src/**"]`. Install `@vitest/coverage-v8`.
- **Exclusions are explicit and reviewed.** Backend: `# pragma: no cover` only with a reason comment.
  Frontend: an `exclude` list in the vitest config limited to things that cannot hold logic (generated
  `api-types.ts`, type-only files, Next.js boilerplate). Any new exclusion appears in the PR diff.
  Optionally add a CI grep that counts `pragma: no cover` and fails on growth.
- **Rollout via ratchet, not a cliff:** measure current coverage, set the threshold to that number
  (rounded down), then raise it as gaps close until it reaches 100 (see §8). Do not turn on 100 while
  CI is red for everyone.

### 5.2 Random order

- **Backend:** `pytest-randomly` (random order of modules, classes and tests, and it also reseeds
  `random`/Faker per test). The seed is printed in the pytest header. Reproduce a failure with
  `pytest --randomly-seed=<seed>`. Locally you can disable it with `-p no:randomly`.
- **Frontend:** vitest `sequence: { shuffle: true }` in config; the seed is printed, and
  `--sequence.seed=<n>` reproduces.
- First run will expose hidden order dependencies. Expected suspects: the shared rate limiter
  (Redis tally; the `SHARED_TALLY_URL` split already exists for this reason), module-level
  singletons, and DB state leaking between tests. Fix the tests, don't pin the order.
- CI uses a fresh seed each run so that bugs surface over time; the seed is always in the log.

### 5.3 Unit-test tree mirrors the source tree

Rule: for every source module there is exactly one unit-test module at the mirrored path.

```
backend/app/services/orders.py          →  backend/tests/unit/app/services/test_orders.py
backend/app/api/v1/shops.py             →  backend/tests/unit/app/api/v1/test_shops.py
frontend/src/lib/format.ts              →  frontend/tests/unit/src/lib/format.test.ts
frontend/src/components/Card.tsx        →  frontend/tests/unit/src/components/Card.test.tsx
```

Details:

- Backend tests for `app/` live under `tests/unit/app/...` with `test_<module>.py`. `__init__.py` and
  pure re-export modules are exempt. (An alternative is dropping the `app/` level, so `tests/unit/services/...`.
  Pick one and write it down; the plan assumes the `app/` level is kept, so the mirror is mechanical.)
- Frontend mirror lives under `frontend/tests/unit/` mirroring `src/`, matching `*.test.ts(x)`.
- **Enforced, not just documented:** a small script `scripts/check-tests-tree.py` (one for each side,
  or one parametrised) run from `lint-back` / `lint-front`. It fails when
  1. a source module has no mirrored test file, or
  2. a test file under `tests/unit/` has no corresponding source module (orphan after a rename/delete).
  An explicit allow-list file (`scripts/tests-tree-exempt.txt`) holds the exemptions, so they are visible in review.
- Existing tests are migrated by moving files, in a PR containing nothing else, so that
  `git mv` history stays readable.
- Benefit beyond tidiness: mutmut maps mutants to tests, and a mirrored tree makes "which test
  should have killed this?" a trivial lookup.

---

## 6. Stage 3: e2e-tests

Purpose: behave like a human clicking in a browser, against the whole real stack. No mocks.

```
npm ci
npx playwright install --with-deps chromium
docker compose up --build -d --wait
docker compose exec backend python -m scripts.grant_role … moderator --reset-password
npx playwright test
```

Changes from today:

- Runs in parallel with the lint and unit jobs (§2); it does not wait for them.
- Playwright `retries: 1` in CI with `trace: 'on-first-retry'`; a test that passes on retry is
  reported as *flaky* and must be fixed, not ignored.
- Keep: playwright-report artifact on failure, `docker compose logs --tail 300` on failure.
- Specs stay as is (`seller-to-catalog`, `production-cookies`). The https-only spec still skips in
  CI; that gap is tracked in §9.
- Rule for this layer: no coverage metric, no mutation testing. Scenario count is kept small and
  each scenario must be a real user journey.

---

## 7. Mutation testing with mutmut (local only for now)

### Scope

- **Backend only.** mutmut is Python-only. A frontend counterpart (Stryker) is a later decision.
- **Local only.** Not in CI, not in `gate`, not in pre-commit. Reason: it is slow and needs tuning
  before its numbers can be trusted.
- Runs against `tests/unit` only (fast, deterministic, no stand).

### Setup

- Dev dependency `mutmut` in the backend's dev group.
- `backend/pyproject.toml`:
  ```toml
  [tool.mutmut]
  paths_to_mutate = ["app/"]
  tests_dir = ["tests/unit/"]
  ```
  Config keys differ between mutmut major versions. Check against the installed version's docs
  when implementing, including how it copies non-Python files the app needs at runtime.
- `.gitignore`: `mutants/` (mutmut's working directory) and any cache files it writes.
- Makefile targets:
  ```
  make mutate                      mutmut run                 (whole app; slow, run rarely)
  make mutate-module M=app.services.orders      run one module (the normal workflow)
  make mutate-report               mutmut results             (list survivors)
  ```
- A short `docs/mutation-testing.md` (Russian, like the rest of the repo docs): how to run, how to read
  survivors, when a survivor is acceptable (equivalent mutant) and when it is a missing assertion.

### How it is used

1. Normal flow: after finishing a module, `make mutate-module M=<module>`, then kill the survivors
   by tightening assertions, or record why a mutant is equivalent.
2. A mutation score is **not** gated and **not** a target yet. First goal is a measured baseline per
   package, written into the doc.
3. Known friction to check during setup: the async/greenlet layer under SQLAlchemy, tests that
   need Postgres/Redis (slow per mutant), and the random-order plugin. If random order interferes with
   mutmut's per-mutant test selection, disable randomly for mutation runs with `-p no:randomly`
   through the mutmut pytest args.

### Later (not in this plan's scope)

- CI: scheduled nightly workflow, or PR-time on changed modules only, reporting survivors as a
  non-blocking comment first, then a score threshold.
- Frontend: evaluate Stryker with vitest.

---

## 8. Rollout order

Each step is its own PR, and each leaves `main` green.

| # | PR | Notes |
| --- | --- | --- |
| 0 | **Baseline.** Measure backend and frontend coverage, count tests, time each lane. Record numbers in the PR description. | No code change. Sets the ratchet starting points. |
| 1 | **Restructure workflows.** New `ci.yml` with the jobs from §2, Makefile targets (`lint-*`, `unit-*`), `gate`, concurrency, timeouts, caches. Old workflows deleted. Still 80% diff-cover, so behaviour is unchanged. | Update branch protection to require `gate` only. |
| 2 | **Random order** (back, front) plus fixes for whatever it exposes. | May be several commits of test fixes. |
| 3 | **Tree mirror.** Move tests with `git mv` only, then add `check-tests-tree` scripts to the lint jobs. | Move PR contains no logic changes. |
| 4 | **Coverage ratchet, backend.** Branch coverage on, `fail_under` at baseline; remove diff-cover; then raise to 100 in steps as gaps are filled; resolve `omit` of `app/main.py`. | Several small PRs are fine. |
| 5 | **Coverage ratchet, frontend.** Install provider, thresholds at baseline, raise to 100. | Same pattern as 4. |
| 6 | **mutmut local.** Dependency, config, Makefile targets, docs, baseline numbers per package. | No CI change. |
| 7 | **e2e tightening.** Retries, traces, flaky reporting. | Optional later: `needs` on the lint jobs only, if runner minutes matter. |

---

## 9. Open questions / decisions needed

1. **Integration tests.** The current 1232 backend tests include `tests/integration` (DB, Redis rate limit,
   etc.). The three-stage model has no "integration" bucket. Default assumed here: they continue
   to run inside `unit-back` with services, contribute to coverage, and the mirror rule applies to
   `tests/unit` only. The alternative is a strict split (pure unit with no services, plus an
   integration job), which is cleaner but a bigger migration and affects what 100% means.
2. **Where 100% is measured.** Unit tests only, or unit + integration combined? This follows
   from question 1.
3. **Exclusion policy.** Agree the list of things allowed to be excluded from coverage (generated files,
   `if TYPE_CHECKING`, `__main__` guards, Next.js boilerplate) before the ratchet starts.
4. **Mirror layout.** Keep the `app/` level under `tests/unit/` or drop it? Same for the frontend `src/` level.
5. **Search service.** Assumed to get `lint-search` / `unit-search` with identical rules (it also
   needs `alembic upgrade head` from `backend/`). Confirm, or leave it as a separate workflow.
6. **Backlog, deliberately out of scope:** prod-image build in CI, https stand and observability
   in a nightly, `deploy-staging.yml`, dependency/security scanning, Dependabot.

---

## 10. Definition of done

- `ci.yml` has exactly the jobs: `lint-back`, `lint-front`, `unit-back`, `unit-front`, `e2e`, `gate`; branch protection requires `gate`.
- `make lint-*` and `make unit-*` are what CI runs; adding a linter touches only the Makefile.
- Backend and frontend coverage gates are at 100% (branch coverage on the backend), with all exclusions explicit.
- Unit tests run in random order on both sides and the seed is visible in logs.
- `check-tests-tree` passes on both sides and runs in CI.
- `make mutate-module` works locally and a baseline mutation report is documented.
- `diff-cover` and the old four workflow files are gone.
