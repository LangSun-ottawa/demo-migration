# Local Keycloak SAML login

This is an optional real SAML integration, not a mock or an alternative business
permission engine. Password login remains available. PW/vulnerability scanners
are deliberately out of scope.

## Start

From repository root:

```bash
.venv/bin/pip install -r requirements.txt
docker compose -f services/keycloak/compose.yaml up -d
# Wait for Keycloak's "Listening on" startup log, then pin its public certificate:
docker compose -f services/keycloak/compose.yaml logs --tail 30
.venv/bin/python services/keycloak/bootstrap.py
.venv/bin/python backend/manage.py migrate
```

Set `SAML_ENABLED=true` in the ignored root `.env`, restart Django. Open
http://127.0.0.1:4200/setup and choose **Sign in with SSO · Keycloak**. If already
logged in, choose **Sign out** first. Use `127.0.0.1` consistently, not localhost:
cookies and the SAML endpoint URLs must match. Keep the other demo services running
as described in README.

| Local account | Password | Access |
| --- | --- | --- |
| sso-reader | LocalReader123! | Read, no business writes |
| sso-writer | LocalWriter123! | Read/write |

Admin console: http://127.0.0.1:8080/admin/ (`demo-admin` /
`LocalKeycloakAdmin123!`). These are public local-demo credentials, not secrets
for deployment. Docker binds only to loopback. The realm is `migration-demo`.
Data persists in the compose named volume. Realm import skips an existing realm;
editing the JSON alone will not update existing users/clients.

Stop without deleting data: `docker compose -f services/keycloak/compose.yaml stop`.
Do not remove the volume to troubleshoot: it contains users and the signing key.

## Flow and code

Angular link → Django `/api/demo/auth/saml/login/` → Keycloak login → signed SAML
POST `/api/demo/auth/saml/acs/` → toolkit validates assertion → Django login()
creates its normal Session → fixed redirect back to Angular `/setup`.
Gateway/Broker/Pi are unchanged; Pi never receives SAML assertions or cookies.

- `services/keycloak/compose.yaml`, `demo-realm.json`: local IdP/client/test users.
- `services/keycloak/bootstrap.py`: fetches only the fixed local metadata URL;
  pins the public certificate in ignored `.local/saml/idp.json`. No private key
  is exported. Rerun explicitly after an intentional IdP signing-key change.
- `backend/demoapp/saml.py`: login, ACS, SP metadata and server-side group mapping.
- `backend/demoapp/models.py`: SamlIdentity and SamlReplay (migration 0007).
- `backend/backend_config/settings.py`: enabled flag, fixed URLs, group mapping.
- Setup component: SSO link, local sign out, clears previous user's UI context.

The identity key is trusted IdP issuer + persistent NameID. New Django users have
an unusable password and an opaque `saml_<hash>` username. No auto-linking by email
or local username. No auto staff/superuser grant. Only `demo-readonly` and
`demo-readwrite` map to the existing demo_setup Groups. Unknown groups grant
nothing; mapped grants are resynchronized at each SAML login. Django checks its
current Groups on every API call; IdP changes do not push revocations into existing
Django sessions until another login. Disable the Django user/revoke its Groups
to deny existing sessions immediately.

Both assertion and response signatures are required, strict XML/protocol checks
are enabled, and request IDs are session-bound with a five-minute limit. No
unsolicited IdP-initiated login; database uniqueness blocks reused assertions.
RelayState is never used as a redirect destination. Only ACS is CSRF-exempt;
normal business writes retain Session authentication + CSRF + FeaturePermission.
Raw assertions/cookies are not logged, stored in conversation history or sent to Pi.

**Sign out is local Django logout, not SAML Single Logout.** The Keycloak SSO
session may remain, so another SSO click can log the same user straight back in.
Use Keycloak's account logout or a separate browser profile to switch IdP users.
Account page: http://127.0.0.1:8080/realms/migration-demo/account/.

## Verification and limits

```bash
cd backend
../.venv/bin/python manage.py test demoapp.test_saml
cd ..
.venv/bin/python services/keycloak/verify.py
```

Unit tests cover identity isolation, group downgrade/unknown groups, disabled
identity, unsolicited/expired flow, readonly API refusal and business CSRF.
The opt-in HTTP verification uses **real Keycloak login and signed responses**,
not mocked toolkit success: reader write 403, writer create/delete cleanup,
replay rejection, local logout and signed-group tampering rejection. It retains
the two SSO identity mappings but deletes its temporary business record.
The HTTP test client emulates Chromium's trustworthy-loopback handling for
Keycloak Secure cookies only on the fixed local realm path; it does not change
server cookie settings. A Chrome SSO redirect back to Angular was also checked.

This configuration is for same-site loopback HTTP development only. Deployment
needs HTTPS, secure cookies, intentional SameSite handling if IdP/SP are on
different sites, private credentials, SP request signing/certificate lifecycle,
session expiry/revocation policy and SLO if required. Do not solve cross-site POST
cookie problems by disabling protocol validation or business CSRF. Review the
[toolkit security guidance](https://github.com/SAML-Toolkits/python3-saml) and
[Keycloak deployment guide](https://www.keycloak.org/server/configuration-production).
