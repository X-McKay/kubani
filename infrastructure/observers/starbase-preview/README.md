# Osprey Starbase preview observer

Osprey is the independent desktop and supervised observer for the
pre-production Starbase synthetic preview. It uses Osprey's existing Tailscale
device identity to pull the private HTTPS endpoint. It has no Kubernetes,
GitHub, provider, or Starbase credential and no mutation authority.

Every successful run verifies all four reviewed Kubani ingress addresses with
the production TLS hostname, the DNS-selected route, anonymous OIDC session
state, and the exact Authentik login redirect. It writes one sanitized local
result after every successful run; no Kubani state, response body, token,
cookie, or one-time OIDC value leaves Osprey.

## Temporary supervised exception

Al McKay authorized local-only observation for the supervised Phase 5 homelab
preview on 2026-08-26. This is deliberately simpler than an external dead-man
receiver and does not provide automatic off-host notification. If Osprey,
Tailscale, or the whole site is unavailable, the gap is discovered at the next
operator checkpoint rather than delivered as an alert.

That limitation is accepted only for the time-bounded, actively supervised
preview. Every unexplained gap restarts the 24-hour clock. A separately
delivered dead-man signal remains required before production or unattended
operation; [issue #90](https://github.com/X-McKay/kubani/issues/90) owns that
decision. This exception does not redefine the accepted production
architecture or prove total-outage detection.

## Install without activating

The reviewed Kubani checkout must exist at `/opt/kubani` at the exact accepted
revision. Copy the two unit files into `/etc/systemd/system/`, then run:

```text
sudo systemctl daemon-reload
sudo systemctl enable starbase-preview-heartbeat.timer
```

Do not start the timer while Starbase is intentionally inert. Verify the units
before activation with `systemd-analyze verify`. The observer has no secret,
credential file, receiver URL, or push path.

After the Phase 5 merge has reconciled and the application checks pass, start
the timer and force one run:

```text
sudo systemctl start starbase-preview-heartbeat.timer
sudo systemctl start starbase-preview-heartbeat.service
systemctl status starbase-preview-heartbeat.service
systemctl list-timers starbase-preview-heartbeat.timer
```

Confirm the forced run succeeded in the service journal before starting the
24-hour observation clock. Logs intentionally contain only a sanitized result.
A failed or missing run is an observation gap and restarts the clock after
recovery.

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

Retain the log, its digest, the corresponding Kubani health/resource sample,
and the checkpoint timestamp together. Confirm the expected five-minute
cadence and investigate every gap; never infer success from a missing local
log. The log is intentionally free of OIDC one-time values, cookies, and
response bodies, but it remains operational evidence and must not be made
public without review.

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

Then remove the two installed unit files and reload systemd. The repository
copies and historical evidence remain. Removing the observer does not mutate
Kubani or Starbase, but the Phase 5 observation window cannot continue without
a restored independent path.
