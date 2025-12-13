# Authentication with Authentik

This guide explains how to configure OAuth2/OIDC authentication with Authentik for services deployed in the cluster.

## Overview

Authentik is deployed at `https://auth.almckay.io` and provides:
- OAuth2/OIDC identity provider
- Single Sign-On (SSO) for all services
- User management and access control
- Application proxy for services without native auth

## Prerequisites

- Authentik deployed and accessible at `https://auth.almckay.io`
- Admin access to Authentik or API token
- The service must support OAuth2/OIDC authentication

## Accessing the Authentik API

### Get API Token

The Authentik API token is stored in the `auth` namespace:

```bash
# Get the Authentik API token
AUTHENTIK_TOKEN=$(kubectl get secret authentik-credentials -n auth -o jsonpath='{.data.authentik-bootstrap-token}' | base64 -d)
```

### Test API Access

```bash
curl -s "https://auth.almckay.io/api/v3/core/users/me/" \
  -H "Authorization: Bearer $AUTHENTIK_TOKEN" | jq .
```

## Creating an OAuth2 Provider

### Step 1: Get Required IDs

Before creating a provider, you need the authorization flow ID and optionally a signing key:

```bash
# List available flows
curl -s "https://auth.almckay.io/api/v3/flows/instances/" \
  -H "Authorization: Bearer $AUTHENTIK_TOKEN" | jq '.results[] | {pk, slug, name}'

# List available certificate/key pairs (for RS256 signing)
curl -s "https://auth.almckay.io/api/v3/crypto/certificatekeypairs/" \
  -H "Authorization: Bearer $AUTHENTIK_TOKEN" | jq '.results[] | {pk, name}'
```

### Step 2: Create OAuth2 Provider

**Important**: Always specify a `signing_key` to use RS256 signing algorithm. Without it, Authentik uses HS256 (symmetric), which many applications don't support.

```bash
# Set variables
APP_NAME="myservice"
EXTERNAL_HOST="https://myservice.almckay.io"
AUTH_FLOW_ID="<authorization-flow-uuid>"   # Usually the 'default-provider-authorization-implicit-consent' flow
SIGNING_KEY_ID="<certificate-keypair-uuid>" # Required for RS256

# Create the OAuth2 provider
curl -s -X POST "https://auth.almckay.io/api/v3/providers/oauth2/" \
  -H "Authorization: Bearer $AUTHENTIK_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"name\": \"${APP_NAME}\",
    \"authorization_flow\": \"${AUTH_FLOW_ID}\",
    \"client_type\": \"confidential\",
    \"client_id\": \"${APP_NAME}\",
    \"redirect_uris\": \"${EXTERNAL_HOST}/auth/callback\\n${EXTERNAL_HOST}/auth/sso/callback\",
    \"signing_key\": \"${SIGNING_KEY_ID}\",
    \"access_token_validity\": \"hours=24\"
  }" | jq .
```

### Step 3: Create Application

After creating the provider, create an application that uses it:

```bash
PROVIDER_PK=<provider-pk-from-above>

curl -s -X POST "https://auth.almckay.io/api/v3/core/applications/" \
  -H "Authorization: Bearer $AUTHENTIK_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"name\": \"${APP_NAME}\",
    \"slug\": \"${APP_NAME}\",
    \"provider\": ${PROVIDER_PK}
  }" | jq .
```

### Step 4: Get Client Credentials

After creating the provider, retrieve the client ID and secret:

```bash
# List OAuth2 providers
curl -s "https://auth.almckay.io/api/v3/providers/oauth2/" \
  -H "Authorization: Bearer $AUTHENTIK_TOKEN" | jq '.results[] | {pk, name, client_id}'

# Get specific provider details (including client_secret)
PROVIDER_PK=<provider-pk>
curl -s "https://auth.almckay.io/api/v3/providers/oauth2/${PROVIDER_PK}/" \
  -H "Authorization: Bearer $AUTHENTIK_TOKEN" | jq '{client_id, client_secret}'
```

## Common OIDC Endpoints

For applications that need OIDC configuration, the standard endpoints are:

| Endpoint | URL |
|----------|-----|
| Issuer | `https://auth.almckay.io/application/o/<app-slug>/` |
| Authorization | `https://auth.almckay.io/application/o/authorize/` |
| Token | `https://auth.almckay.io/application/o/token/` |
| UserInfo | `https://auth.almckay.io/application/o/userinfo/` |
| JWKS | `https://auth.almckay.io/application/o/<app-slug>/jwks/` |
| OpenID Configuration | `https://auth.almckay.io/application/o/<app-slug>/.well-known/openid-configuration` |

## JWT Signing Algorithm: RS256 vs HS256

### The Problem

Many applications expect JWT tokens signed with RS256 (asymmetric RSA signing), but Authentik defaults to HS256 (symmetric signing with client secret) when no signing key is configured.

**Symptom**: Authentication fails with errors like:
```
oidc: malformed jwt: go-jose/go-jose: unexpected signature algorithm "HS256"; expected ["RS256"]
```

### The Solution

Ensure the OAuth2 provider has a `signing_key` configured. This tells Authentik to use RS256.

#### Check Current Provider Configuration

```bash
# List all OAuth2 providers with signing key status
curl -s "https://auth.almckay.io/api/v3/providers/oauth2/" \
  -H "Authorization: Bearer $AUTHENTIK_TOKEN" | jq '.results[] | {pk, name, signing_key}'
```

A provider with `"signing_key": null` uses HS256. Providers with a UUID use RS256.

#### Fix Existing Provider

```bash
# Get available signing keys
SIGNING_KEY=$(curl -s "https://auth.almckay.io/api/v3/crypto/certificatekeypairs/" \
  -H "Authorization: Bearer $AUTHENTIK_TOKEN" | jq -r '.results[0].pk')

# Update the provider to use RS256
PROVIDER_PK=<provider-pk>
curl -s -X PATCH "https://auth.almckay.io/api/v3/providers/oauth2/${PROVIDER_PK}/" \
  -H "Authorization: Bearer $AUTHENTIK_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"signing_key\": \"${SIGNING_KEY}\"}" | jq .
```

## Managing OAuth2 Providers

### List All Providers

```bash
curl -s "https://auth.almckay.io/api/v3/providers/oauth2/" \
  -H "Authorization: Bearer $AUTHENTIK_TOKEN" | jq '.results[] | {pk, name, client_id, signing_key}'
```

### Get Provider Details

```bash
PROVIDER_PK=<provider-pk>
curl -s "https://auth.almckay.io/api/v3/providers/oauth2/${PROVIDER_PK}/" \
  -H "Authorization: Bearer $AUTHENTIK_TOKEN" | jq .
```

### Update Provider

```bash
PROVIDER_PK=<provider-pk>
curl -s -X PATCH "https://auth.almckay.io/api/v3/providers/oauth2/${PROVIDER_PK}/" \
  -H "Authorization: Bearer $AUTHENTIK_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "redirect_uris": "https://newapp.almckay.io/callback"
  }' | jq .
```

### Delete Provider

```bash
PROVIDER_PK=<provider-pk>
curl -s -X DELETE "https://auth.almckay.io/api/v3/providers/oauth2/${PROVIDER_PK}/" \
  -H "Authorization: Bearer $AUTHENTIK_TOKEN"
```

## Configuring Applications

### Kubernetes Secret for OAuth Credentials

Create a SOPS-encrypted secret with OAuth credentials:

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: myservice-credentials
  namespace: myservice
type: Opaque
stringData:
  oauth-client-id: <client-id>
  oauth-client-secret: <client-secret>
```

Encrypt with SOPS:

```bash
sops --encrypt --in-place gitops/apps/myservice/secret.enc.yaml
```

### Example: HelmRelease with OAuth

```yaml
apiVersion: helm.toolkit.fluxcd.io/v2
kind: HelmRelease
metadata:
  name: myservice
  namespace: myservice
spec:
  values:
    auth:
      enabled: true
      oidc:
        issuerUrl: "https://auth.almckay.io/application/o/myservice/"
        clientId:
          secretKeyRef:
            name: myservice-credentials
            key: oauth-client-id
        clientSecret:
          secretKeyRef:
            name: myservice-credentials
            key: oauth-client-secret
        callbackUrl: "https://myservice.almckay.io/auth/callback"
```

### Example: Environment Variables

```yaml
env:
  - name: OIDC_ENABLED
    value: "true"
  - name: OIDC_PROVIDER_URL
    value: "https://auth.almckay.io/application/o/myservice/"
  - name: OIDC_CLIENT_ID
    valueFrom:
      secretKeyRef:
        name: myservice-credentials
        key: oauth-client-id
  - name: OIDC_CLIENT_SECRET
    valueFrom:
      secretKeyRef:
        name: myservice-credentials
        key: oauth-client-secret
  - name: OIDC_CALLBACK_URL
    value: "https://myservice.almckay.io/auth/callback"
```

## Troubleshooting

### Error: "unexpected signature algorithm HS256; expected RS256"

**Cause**: The OAuth2 provider doesn't have a signing key configured.

**Fix**: Update the provider with a signing key (see "Fix Existing Provider" section above).

### Error: "redirect_uri_mismatch"

**Cause**: The callback URL in the application doesn't match what's configured in Authentik.

**Fix**:
1. Check the redirect URIs configured in the provider:
   ```bash
   curl -s "https://auth.almckay.io/api/v3/providers/oauth2/${PROVIDER_PK}/" \
     -H "Authorization: Bearer $AUTHENTIK_TOKEN" | jq '.redirect_uris'
   ```
2. Update to include the correct callback URL:
   ```bash
   curl -s -X PATCH "https://auth.almckay.io/api/v3/providers/oauth2/${PROVIDER_PK}/" \
     -H "Authorization: Bearer $AUTHENTIK_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"redirect_uris": "https://myservice.almckay.io/auth/callback\nhttps://myservice.almckay.io/auth/sso/callback"}'
   ```

### Error: "invalid_client"

**Cause**: Incorrect client ID or client secret.

**Fix**:
1. Verify the client credentials in the secret match the provider:
   ```bash
   # Check what's in Kubernetes
   kubectl get secret myservice-credentials -n myservice -o jsonpath='{.data.oauth-client-id}' | base64 -d

   # Check what's in Authentik
   curl -s "https://auth.almckay.io/api/v3/providers/oauth2/${PROVIDER_PK}/" \
     -H "Authorization: Bearer $AUTHENTIK_TOKEN" | jq '{client_id, client_secret}'
   ```

### Cannot Find API Token

The Authentik bootstrap token is stored in different locations depending on deployment:

```bash
# Try auth namespace (current deployment)
kubectl get secret authentik-credentials -n auth -o jsonpath='{.data.authentik-bootstrap-token}' | base64 -d

# Try authentik namespace (alternative)
kubectl get secret authentik-credentials -n authentik -o jsonpath='{.data.authentik-bootstrap-token}' | base64 -d
```

## Quick Reference

### Service Integration Checklist

1. [ ] Create OAuth2 provider in Authentik with RS256 signing key
2. [ ] Create application linked to the provider
3. [ ] Note the client ID and client secret
4. [ ] Create SOPS-encrypted Kubernetes secret with credentials
5. [ ] Configure the application with OIDC settings
6. [ ] Add DNS record for the service
7. [ ] Deploy and test authentication flow

### Required Information for New Service

| Item | Example |
|------|---------|
| Service name | `temporal` |
| External URL | `https://temporal.almckay.io` |
| Callback URL(s) | `https://temporal.almckay.io/auth/sso/callback` |
| Authorization flow | `default-provider-authorization-implicit-consent` |
| Signing key | Use existing certificate keypair |

## Related Documentation

- [DNS Configuration](./DNS_CONFIGURATION.md) - How to set up DNS records for services
- [Authentik Admin Interface](https://auth.almckay.io/if/admin/) - Web-based management
- [Authentik API Documentation](https://auth.almckay.io/api/v3/docs/) - Full API reference
