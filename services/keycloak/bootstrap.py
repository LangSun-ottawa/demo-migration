"""Pin the local IdP certificate after starting the loopback-only Keycloak demo."""
import json
import os
from pathlib import Path

import httpx
from onelogin.saml2.idp_metadata_parser import OneLogin_Saml2_IdPMetadataParser


def main():
    url = 'http://127.0.0.1:8080/realms/migration-demo/protocol/saml/descriptor'
    response = httpx.get(url, timeout=15)
    response.raise_for_status()
    config = OneLogin_Saml2_IdPMetadataParser.parse(response.text)
    target = Path(__file__).resolve().parents[2] / '.local/saml/idp.json'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(config['idp'], indent=2) + '\n')
    os.chmod(target, 0o600)
    print('Pinned local Keycloak metadata at .local/saml/idp.json (no private keys).')


if __name__ == '__main__':
    main()
