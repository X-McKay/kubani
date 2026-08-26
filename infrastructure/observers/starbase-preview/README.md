# Osprey Starbase preview observer

Osprey is the independent desktop and heartbeat observer for the pre-production
Starbase synthetic preview. It uses Osprey's existing Tailscale device identity
to pull the private HTTPS endpoint. It has no Kubernetes, GitHub, provider, or
Starbase credential and no mutation authority.

Every successful run verifies all four reviewed Kubani ingress addresses with
the production TLS hostname, the DNS-selected route, anonymous OIDC session
state, and the exact Authentik login redirect. Only after every check passes
does it send an empty success ping to an independent dead-man receiver. A
missing ping is the alert; no Kubani state, response body, token, cookie, or
one-time OIDC value is transmitted.

## External prerequisite

Create a dedicated Healthchecks.io check with a five-minute period, a
two-minute grace period, and an email notification owned by Al McKay. Treat its
unique `https://hc-ping.com/...` URL as a secret. Store only that URL on Osprey
at `/etc/starbase-preview-heartbeat/ping-url`, owned by root with mode `0600`.
Do not put it in Git, GitHub, shell history, screenshots, or logs.

Before relying on the receiver, send one isolated test ping and deliberately
miss one period to prove both recovery and notification delivery. Account and
notification setup are operator actions outside this repository.

## Install without activating

The reviewed Kubani checkout must exist at `/opt/kubani` at the exact accepted
revision. Copy the two unit files into `/etc/systemd/system/`, then run:

```text
sudo systemctl daemon-reload
sudo systemctl enable starbase-preview-heartbeat.timer
```

Do not start the timer while Starbase is intentionally inert. Verify the unit
before activation with `systemd-analyze verify`, confirm the secret file's
owner and mode without printing it, and use the script's `--no-push` mode only
for an authorized live endpoint check.

After the Phase 5 merge has reconciled and the application checks pass, start
the timer and force one run:

```text
sudo systemctl start starbase-preview-heartbeat.timer
sudo systemctl start starbase-preview-heartbeat.service
systemctl status starbase-preview-heartbeat.service
systemctl list-timers starbase-preview-heartbeat.timer
```

Confirm the receiver recorded that run before starting the 24-hour observation
clock. Logs intentionally contain only a sanitized result. A failed or missing
run is an observation gap and restarts the clock after recovery.

## Evidence retention

Record the observation window's UTC start and end. Journald rotation on a
desktop is not durable evidence, so export the sanitized service journal to the
protected evidence store every six hours, immediately before any rollback, and
at the end of the window. Replace both timestamps with the exact checkpoint:

```text
sudo journalctl --unit=starbase-preview-heartbeat.service \
  --since='<window-start UTC>' --until='<checkpoint UTC>' \
  --output=short-iso-precise --no-pager \
  > starbase-preview-heartbeat.log
sha256sum starbase-preview-heartbeat.log
```

Retain the log, its digest, the receiver's corresponding history export or
secret-free screenshot, and the checkpoint timestamp together. Confirm the
expected five-minute cadence and investigate every gap; never infer success
from a missing local log. The log is intentionally free of the receiver URL,
OIDC one-time values, cookies, and response bodies, but it remains operational
evidence and must not be made public without review.

## Desktop validation

From Osprey's desktop browser, navigate directly to
`https://starbase.almckay.io` and retain timestamped, secret-free evidence for:

1. valid TLS and successful Authentik login as an authorized operator;
2. the authenticated Starbase UI and unmistakable synthetic source/item labels;
3. API/SSE reconnect without duplicate durable data;
4. logout followed by unauthenticated denial; and
5. stale-session denial after the separately authorized session exercise.

Screenshots must exclude cookies, tokens, browser storage, and private account
details. This human journey complements the credential-free heartbeat; it does
not turn Osprey into a cluster administration host.

## Stop and remove

Stop first and retain relevant sanitized logs:

```text
sudo systemctl disable --now starbase-preview-heartbeat.timer
sudo systemctl reset-failed starbase-preview-heartbeat.service
```

Then remove the two installed unit files and the local ping URL, reload systemd,
and delete the external check. The repository copies and historical evidence
remain. Removing the observer does not mutate Kubani or Starbase, but the Phase
5 observation window cannot continue without a restored independent path.
