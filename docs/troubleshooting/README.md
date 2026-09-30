# Troubleshooting Guides

Focused operational writeups for recurring cluster issues.

## Available Guides

- [Flannel Routes Lost After Tailscale Upgrade](flannel-routes-lost-after-tailscale-upgrade.md)
- [UFW block logs for pod traffic](ufw-block-logs-for-pod-traffic.md) — `[UFW BLOCK] IN=cni0 OUT=flannel.1` records are benign; why iptables counters cannot be trusted on these hosts.
- [vLLM main engine hang on GB10](vllm-main-engine-hang-gb10.md) — `/v1/models` answers but completions hang forever; EngineCore wedged in a CUDA kernel while `/health` stays green. Recognise, recover, and the 2026-09-25 Xid 13 incident record.

## Writing a new troubleshooting doc

Start from [`_template.md`](_template.md) — the structure the GB10 runbook
above uses (one-line answer, how to recognise it, a dated incident record,
working hypothesis, why the cluster did not heal itself, and a follow-ups
checklist mirrored as GitHub issues labelled `follow-up`). The
`incident-capture` skill drafts a new record from this template using the
forensics it captures before a restart.
