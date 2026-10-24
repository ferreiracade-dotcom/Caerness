# Caerness connector

A local MCP server so the Claude desktop app can play Caerness. Claude is the game master; the engine is memory and consequence.

1. Install requirements: `python -m pip install -r connector/requirements.txt` (Python 3.13).
2. Create a campaign and choose the protagonist:
   `python connector/setup_campaign.py --campaign main --actor "<full name>"`
   (campaigns are copies of `data/caerness.db` under `%LOCALAPPDATA%\Caerness\campaigns`).
3. Add this to `%APPDATA%\Claude\claude_desktop_config.json` (merge with any existing servers):
   ```json
   {"mcpServers": {"caerness": {
     "command": "C:\\Users\\NozzE\\AppData\\Local\\Programs\\Python\\Python313\\python.exe",
     "args": ["D:\\Code\\Caerness\\connector\\run_server.py"],
     "env": {"CAERNESS_CAMPAIGN": "main"}}}}
   ```
4. Restart the Claude desktop app.
5. In a new chat type `resume`.

Tools: `resume`, `scene`, `lookup`, `act`, `advance`, `note`. Mutating tools need a fresh `call_id`; reuse it only to retry the same call. Stdout is the protocol channel, so everything the engine prints is sent to stderr.

Note: the SDK pinned here is mcp 2.x, where `FastMCP` is named `MCPServer` (`mcp.server.mcpserver`).

## Remote hosting (Oracle Cloud Always Free)

The same server can run on a small VM and be used from any Claude app, phone included, as a custom connector. Design and reasons: `docs/superpowers/plans/2026-10-16-remote-connector-oracle.md`. With no flag `run_server.py` still serves stdio exactly as above; `--transport http` serves Streamable HTTP on `127.0.0.1:8765` behind Caddy, with a single-owner OAuth login (a passphrase page).

Files: `deploy/` (units, Caddyfile, `install.sh`, `update.sh`, `duckdns-update.sh`), `connector/set_passphrase.py`, `connector/backup.py`, `connector/import_campaign.py`, `tools/export_campaign.py`. On the VM: code `/opt/caerness`, state `/var/lib/caerness/{campaigns,backups,auth.db}`, secrets `/etc/caerness/{caerness.env,host.env}`.

### Owner manual steps (steps 1 to 7 need your identity, card and console; the rest is scripted)

1. **Oracle sign-up.** Create an Oracle Cloud Free Tier account (card and phone verification; a small authorization hold is normal). Pick the **home region** carefully (it cannot be changed, and Always Free resources must live there); choose one with Ampere A1 capacity near you. If A1 shows "Out of host capacity", retry later or in another availability domain, or use the AMD micro fallback.
2. **(Recommended) Upgrade to Pay As You Go**, then in Billing set a **budget alert at 1 USD**. This is the documented way to avoid idle-instance reclamation; usage within the Always Free limits is not charged (this is a third-party copy of an Oracle notice: re-check Oracle's Free Tier page when you upgrade). Create only the one instance and the default 50 GB boot volume described below.
3. **SSH key.** On the laptop: `ssh-keygen -t ed25519`; keep the private key, paste the public key in the next step.
4. **Create the VM.** Compute > Create instance: image **Ubuntu 24.04 (arm64)**, shape **VM.Standard.A1.Flex, 1 OCPU, 6 GB**, public IPv4, paste the public key, boot volume 50 GB.
5. **Open the network.** In the VCN's default security list add ingress TCP **80** and **443** from `0.0.0.0/0` (keep 22 as is; optionally restrict 22 to your own IP).
6. **DuckDNS name.** Sign in at https://www.duckdns.org with GitHub or Google, create a subdomain with a random-looking name (for example `caerness-k7q3m9`), set its IP to the VM's public IP, and copy the account token. Keep both.
7. **Choose the passphrase** for the game (12+ characters, not reused anywhere). You will type it once on the VM and once on the claude.ai login page.
8. **SSH in and run** `git clone https://github.com/ferreiracade-dotcom/Caerness.git` then `sudo BRANCH=<branch> Caerness/deploy/install.sh <HOST>` (use `BRANCH=feat/claude-connector` or `feat/remote-connector` until it is merged; read the script first). It prompts for the DuckDNS token. When it says no passphrase is configured, run `sudo -u caerness /opt/caerness/.venv/bin/python -m connector.set_passphrase`, replace the `CHANGE_ME` line in `/etc/caerness/caerness.env` with the printed `CAERNESS_PASSPHRASE_HASH=...` line, then `sudo systemctl restart caerness`.
9. **Copy the campaign up** (laptop, PowerShell; the desktop Claude app may stay open, the export uses SQLite's backup API): `python tools/export_campaign.py --campaign ansel --out $env:TEMP\ansel-export.db`, then `scp -i <key> $env:TEMP\ansel-export.db ubuntu@<ip>:/tmp/`, and on the VM `sudo -u caerness env CAERNESS_CAMPAIGN_DIR=/var/lib/caerness/campaigns /opt/caerness/.venv/bin/python -m connector.import_campaign /tmp/ansel-export.db --campaign ansel`. Set `CAERNESS_CAMPAIGN=ansel` in `/etc/caerness/caerness.env` and `sudo systemctl restart caerness`. Delete `/tmp/ansel-export.db` afterwards.
10. **Add the connector on claude.ai** in a browser: Customize > Connectors > Add custom connector, URL `https://<HOST>/mcp`, Authentication "Sign in now", OAuth client "Register automatically" (fall back to "Use Claude's published identity" if offered and registration is refused). The login page asks for your passphrase and returns you to claude.ai with the connector Connected. From now on the laptop copy of `ansel` is a stale archive: play only through the connector (two copies diverge; `export_campaign` is one-way, laptop to VM).
11. **Phone check.** In the Claude app (same account): New chat, **+** > Connectors, Caerness on, type `resume`. Whether the mobile app can *add* a connector is unverified, which is why step 10 is done in a browser.
12. **To update later:** SSH in and run `sudo /opt/caerness/deploy/update.sh` (pull, install, smoke tests, then restart; a failing step stops before the restart).

### Backups and restore

Snapshots use SQLite's backup API (never a file copy), are integrity-checked, and are kept in `/var/lib/caerness/backups` as `<campaign>-<UTC time>-<label>.db`: a `daily` one at 04:30 UTC (`caerness-backup.timer`; 7 daily plus one per older week for 4 weeks), a throttled `preadvance` one before an `advance` (newest 5), and a `preimport` one whenever an import replaces a campaign (newest 3). An `advance` is refused if its pre-advance snapshot fails the integrity check.

Fetch one to the laptop: `scp -i <key> ubuntu@<ip>:/var/lib/caerness/backups/<file> .`

Restore a snapshot on the VM:
1. `sudo systemctl stop caerness`
2. `sudo -u caerness env CAERNESS_CAMPAIGN_DIR=/var/lib/caerness/campaigns CAERNESS_BACKUP_DIR=/var/lib/caerness/backups /opt/caerness/.venv/bin/python -m connector.import_campaign /var/lib/caerness/backups/<file> --campaign NAME --replace` (the current file is first kept as a `preimport` snapshot)
3. `sudo systemctl start caerness`

### Troubleshooting

| Symptom | Check |
|---|---|
| "Couldn't reach the MCP server" | `curl https://HOST/health` from anywhere; `systemctl status caerness caddy`; `journalctl -u caddy` (certificate or port 80/443 problems); DNS still points at the VM (`duckdns.service`); the VCN security list and the instance firewall (`iptables -S INPUT`) allow 80 and 443 |
| "Authorization with the MCP server failed" | Login locked after 5 wrong passphrases (wait 15 minutes); wrong passphrase; the redirect URI is not `https://claude.ai/api/mcp/auth_callback`; `CAERNESS_PUBLIC_URL` differs from the URL typed into claude.ai (it must match exactly, with no trailing slash) |
| `421` in `journalctl -u caerness` | The Host header is not the public host: `CAERNESS_PUBLIC_URL` is wrong or the request bypassed Caddy |
| Service restarts every 3 seconds | `journalctl -u caerness`: usually a missing or placeholder `CAERNESS_PASSPHRASE_HASH` |
| Tool times out after 240 s | Lower `CAERNESS_MAX_ADVANCE_DAYS` in `/etc/caerness/caerness.env` (default and hard maximum 30), restart |
| Signed out after a long time | Refresh tokens last 90 days and rotate on use; sign in again from the connector's settings |

## World packages: Caerness or Saint Jude

A new campaign copies its package's opening world: `data/caerness.db` for Caerness, `data/saintjude.db` for Saint Jude (rebuild with `python tools/build_opening.py --package saintjude`). The server's campaign (`CAERNESS_CAMPAIGN`, default `main`) is created in the package named by `CAERNESS_WORLD_PACKAGE` (unset means Caerness). Once a campaign exists, its package is the one recorded in its database, whatever the variable says. To play Saint Jude on the VM, ship `data/saintjude.db` with the update, set `CAERNESS_WORLD_PACKAGE=saintjude` and a new `CAERNESS_CAMPAIGN` name in `/etc/caerness/caerness.env`, and restart `caerness` (switch the two back to return to the Caerness campaign). Existing Caerness campaigns need nothing.

## New campaigns: the protagonist

A campaign with no protagonist answers `resume` with `needs_character` and the world package's creation text (`worlds/<id>/creation_section.md`). The GM designs the person with the player and calls `author` with `kind="protagonist"` (preview with `accept=false`, then `accept=true`). The engine only vetoes contradictions (`engine/veto.py`), scales down what the place cannot supply, and fills a lived past (`engine/new_character.py`). `python tools/give_lived_past.py --campaign NAME [--apply]` gives an existing protagonist the same kind of past.
