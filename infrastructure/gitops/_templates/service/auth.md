# Auth for SERVICE_NAME

Fill this in before the service reaches an Ingress, and copy the finished
row into the auth inventory in
`docs/infrastructure/configuration/authentik-app-access.md`.

## Decision table row

Pick the one row of the auth decision table
(`docs/infrastructure/configuration/authentik-app-access.md#decision-table`)
that matches this service's client and surface:

| Client | Surface | Mechanism | Where configured |
|---|---|---|---|
| REPLACE_ME | REPLACE_ME | REPLACE_ME | REPLACE_ME |

## Why this row

<One or two sentences: what kind of client hits this service, and why the
mechanism above rather than one of the other five rows.>

## Configuration

<OIDC client name / Authentik application name / forwardAuth middleware /
gateway virtual key name / "none, tailnet-only" — whichever applies.>

## Auth inventory entry

Add this row to the auth inventory table once the Ingress and (if
applicable) the Authentik blueprint or gateway key are live:

| Hostname | Row | Authentik application or gateway key | Last rotated | Notes |
|---|---|---|---|---|
| SERVICE_NAME.almckay.io | REPLACE_ME | REPLACE_ME | REPLACE_ME | REPLACE_ME |
