# launchd Smoke Summary

- Domain: `gui/501`
- Label: `io.duecheck.sync`
- Install path: real `launchctl bootstrap` via `duecheck schedule install`
- Execution trigger: `launchctl kickstart -k gui/501/io.duecheck.sync`
- Removal path: `duecheck schedule remove`

Observed results:

- `install.json` recorded the expected plist, runner, and log paths
- `status_before.json` reported `loaded: true`
- `launchctl_print_after.txt` showed:
  - `state = running`
  - `runs = 1`
  - `execs = 1`
  - `program = .../run-scheduled-sync.sh`
- `remove.json` confirmed plist and runner removal

Controlled sync target:

- `http://127.0.0.1:9`
- chosen so the scheduled job could execute in the real launchd domain and fail fast without touching live Canvas data
