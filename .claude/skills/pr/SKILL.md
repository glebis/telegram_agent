## /pr - Create a Pull Request

Create a pull request for the current branch with linting, tests, and conventional commit.

### Steps

1. **Confirm branch**: Run `git branch --show-current`. If on `main`, ask the user for a feature branch name (e.g. `feature/add-xyz`). Create the branch with `git checkout -b <name>`, then continue with the PR flow.

2. **Lint**: Run `python -m flake8 src/ tests/`. If there are violations, fix them automatically using `python -m black src/ tests/ && python -m isort src/ tests/`, then re-run flake8. If violations remain, fix the code and repeat until clean.

3. **Test**: Run `python -m pytest tests/ -v`. If tests fail, investigate and fix. Known pre-existing failures to ignore:
   - `test_body_limit_blocks_large_payloads[/api/health]`
   - `test_heartbeat_requires_admin`
   - `test_heartbeat_admin_triggers_run`

4. **Stage & Commit**: Stage all changed files and commit with a conventional commit message (e.g. `feat:`, `fix:`, `refactor:`, `docs:`, `chore:`). Ask the user for the commit message if the intent is unclear.

5. **Push**: Push to the current branch with `git push -u origin HEAD`.

6. **Create PR**: Run `gh pr create --fill` to create the pull request. If `--fill` produces an inadequate title/body, use `gh pr create --title "..." --body "..."` with a proper summary.

7. **Report**: Display the PR URL to the user.

### Environment Notes
- Python: `/opt/homebrew/bin/python3.11`
- Formatters: `python -m black`, `python -m isort`
- Linter: `python -m flake8`
- Tests: `python -m pytest`
