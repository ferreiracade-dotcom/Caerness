# VM runbook: world switching (Caerness + Saint Jude)

Owner runs this on the VM over SSH. No secrets or tokens appear here. The VM currently runs `feat/claude-connector`.

What changes: `resume(world=...)` switches campaigns (Caerness keeps `main.db`; Saint Jude gets `saintjude.db`, created from the tracked `data/saintjude.db`), start-up reopens the last-played world from `/var/lib/caerness/campaigns/last_campaign`, the daily backup now snapshots every campaign (`--all`), and `update.sh` also smoke-runs `tests/connector_world_switch_test.py`. The first start on the new code runs a schema migration on `main.db`, which is why steps 1 and 2 come first.

## 0. The branch must be on GitHub first

The VM can only pull what is pushed. On the laptop, push `feat/world-packages-saintjude` (or ask Claude to push it). Do not start step 3 until it is on origin.

## 1. Back up the live campaign

The label must be one of `daily`, `preadvance`, `manual`, `preimport`; use `manual`.

```bash
sudo -u caerness env CAERNESS_CAMPAIGN_DIR=/var/lib/caerness/campaigns CAERNESS_BACKUP_DIR=/var/lib/caerness/backups /opt/caerness/.venv/bin/python -m connector.backup --campaign main --label manual
```

Find the newest `main` snapshot (this is the one to use below and for rollback; it prints as `main-<UTC time>-manual.db`):

```bash
sudo sh -c 'ls -t /var/lib/caerness/backups/main-*.db | head -1'
```

## 2. Rehearse on a copy (as the service user, nothing real is touched)

Put the newest snapshot in a scratch campaign dir as `main.db`, then run the new code against it. This exercises the schema migration, `resume`, `scene` and a one-day `advance`. Backups go to a scratch dir, not the real one.

The new code is not on the VM until step 3, so first fetch it and check out the branch, tracking origin so `update.sh`'s `git pull --ff-only` works (the VM is on `feat/claude-connector`; the service keeps running the old code in memory until the restart in step 3):

```bash
git -C /opt/caerness fetch origin
```

```bash
git -C /opt/caerness checkout -B feat/world-packages-saintjude --track origin/feat/world-packages-saintjude
```

Create the scratch dir and copy the snapshot in:

```bash
S=$(sudo mktemp -d) && sudo chown caerness:caerness "$S" && sudo -u caerness mkdir "$S/campaigns" "$S/backups" && sudo -u caerness cp "$(sudo sh -c 'ls -t /var/lib/caerness/backups/main-*.db | head -1')" "$S/campaigns/main.db" && echo "$S"
```

Run the rehearsal with the same shell variable `S` (it fails loudly on any `error` key):

```bash
sudo -u caerness env CAERNESS_CAMPAIGN_DIR="$S/campaigns" CAERNESS_BACKUP_DIR="$S/backups" CAERNESS_CAMPAIGN=main CAERNESS_MAX_ADVANCE_DAYS=30 TMPDIR="$S" PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/opt/caerness /opt/caerness/.venv/bin/python - <<'PY'
import uuid
from connector import server

def check(name, result):
    print(name, "->", "ok" if "error" not in result else result)
    if "error" in result:
        raise SystemExit(f"rehearsal failed at {name}: {result['error']}")
    return result

r = check("resume", server.resume(world="caerness"))
print("world:", r.get("world"))
check("scene", server.scene())
check("advance", server.advance(str(uuid.uuid4()), 1, "rehearsal"))
print("REHEARSAL OK")
PY
```

Anything other than `REHEARSAL OK` stops the runbook here: do not continue, send Claude the output. Clean up when done:

```bash
sudo rm -rf "$S"
```

## 3. Deploy

`update.sh` pulls, installs dependencies, runs the three smoke tests against a throwaway dir, restarts `caerness` and checks `/health`. A failing step stops before the restart.

```bash
sudo /opt/caerness/deploy/update.sh
```

## 4. Install the changed backup unit and restart its timer

`update.sh` does not copy unit files, and the new `caerness-backup.service` uses `--all`, so install it first:

```bash
sudo install -m 644 /opt/caerness/deploy/caerness-backup.service /etc/systemd/system/
```

```bash
sudo systemctl daemon-reload
```

```bash
sudo systemctl restart caerness-backup.timer
```

Optional check that the backup service works for every campaign (writes real `daily` snapshots):

```bash
sudo systemctl start caerness-backup.service && journalctl -u caerness-backup.service -n 5 --no-pager
```

## 5. Check from the phone

In the Claude app, new chat, Caerness connector on:

1. "resume Caerness": same scene as before step 1.
2. "resume Saint Jude": a new campaign; it asks for a character.
3. "resume Caerness" again to confirm switching back works.

## Rollback

Restores both the code and the `main` campaign (the new code migrated `main.db`, so old code needs the pre-switch snapshot). Use the snapshot from step 1 (`sudo sh -c 'ls -t /var/lib/caerness/backups/main-*-manual.db | head -1'`).

```bash
sudo systemctl stop caerness
```

```bash
git -C /opt/caerness checkout feat/claude-connector
```

```bash
sudo -u caerness env CAERNESS_CAMPAIGN_DIR=/var/lib/caerness/campaigns CAERNESS_BACKUP_DIR=/var/lib/caerness/backups /opt/caerness/.venv/bin/python -m connector.import_campaign "$(sudo sh -c 'ls -t /var/lib/caerness/backups/main-*-manual.db | head -1')" --campaign main --replace
```

The old backup code has no `--all`, so put the old unit back before the timer next fires:

```bash
sudo install -m 644 /opt/caerness/deploy/caerness-backup.service /etc/systemd/system/ && sudo systemctl daemon-reload
```

```bash
sudo systemctl start caerness
```

`last_campaign` and `saintjude.db` are harmless to the old code: it never reads `last_campaign` and opens only the configured campaign (`CAERNESS_CAMPAIGN=main`). To leave nothing behind anyway (this discards any Saint Jude play; copy `saintjude.db` aside first if you want it):

```bash
sudo rm -f /var/lib/caerness/campaigns/last_campaign /var/lib/caerness/campaigns/saintjude.db
```
