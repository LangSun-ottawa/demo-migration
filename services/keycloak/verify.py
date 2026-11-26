"""Real loopback-only SAML/Keycloak proof; never prints assertions/cookies."""
import base64
import re
from html.parser import HTMLParser

import httpx


class Forms(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.action = ''
        self.fields = {}
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'form':
            self.action = attrs.get('action', '')
        if tag == 'input' and attrs.get('name'):
            self.fields[attrs['name']] = attrs.get('value', '')


def assertion(client, username, password):
    page = client.get('http://127.0.0.1:8001/api/demo/auth/saml/login/', follow_redirects=True)
    page.raise_for_status()
    form = Forms(page.text)
    assert form.action.startswith('http://127.0.0.1:8080/realms/migration-demo/'), 'Expected Keycloak login form'
    # Chromium treats loopback as trustworthy for Secure cookies; httpx does not.
    # Emulate that browser behavior ONLY in this fixed loopback test client.
    for cookie in client.cookies.jar:
        if cookie.domain == '127.0.0.1' and cookie.path.startswith('/realms/migration-demo/'):
            cookie.secure = False
    page = client.post(form.action, data={**form.fields, 'username': username, 'password': password}, follow_redirects=True)
    page.raise_for_status()
    form = Forms(page.text)
    assert form.action == 'http://127.0.0.1:8001/api/demo/auth/saml/acs/', 'Expected fixed Django ACS'
    assert 'SAMLResponse' in form.fields, 'Keycloak did not issue a SAML assertion'
    return form


def main():
    for username, password, writable in [
        ('sso-reader', 'LocalReader123!', False),
        ('sso-writer', 'LocalWriter123!', True),
    ]:
        with httpx.Client(timeout=30) as client:
            form = assertion(client, username, password)
            response = client.post(form.action, data=form.fields)
            assert response.status_code == 302, f'{username}: ACS rejected ({response.status_code})'
            assert response.headers['location'] == 'http://127.0.0.1:4200/setup'
            session = client.get('http://127.0.0.1:8001/api/demo/auth/session').json()
            assert session['result']['authenticated']
            assert client.get('http://127.0.0.1:8001/api/demo/secure/setup').status_code == 200
            headers = {'X-CSRFToken': client.cookies['csrftoken'], 'Origin': 'http://127.0.0.1:4200'}
            response = client.post('http://127.0.0.1:8001/api/demo/secure/setup/profiles',
                                   json={'name': 'SAML verification temporary profile', 'access_level': 'readonly'}, headers=headers)
            assert response.status_code == (200 if writable else 403), f'Unexpected permission result {response.status_code}'
            if writable:
                record_id = response.json()['result']['created_record']['record']['id']
                assert client.delete(f'http://127.0.0.1:8001/api/demo/secure/setup/profiles/{record_id}', headers=headers).status_code == 200
            assert client.post(form.action, data=form.fields).status_code == 400, 'Replay accepted'
            assert client.post('http://127.0.0.1:8001/api/demo/auth/logout', json={}, headers=headers).status_code == 200
            assert not client.get('http://127.0.0.1:8001/api/demo/auth/session').json()['result']['authenticated']
            print(f'{username}: real SAML login, read, {"write + cleanup" if writable else "write denied 403"}, replay rejection and local logout passed')

    with httpx.Client(timeout=30) as client:
        form = assertion(client, 'sso-reader', 'LocalReader123!')
        xml = base64.b64decode(form.fields['SAMLResponse']).decode()
        xml, changed = re.subn(r'>demo-readonly<', '>demo-readwrite<', xml)
        assert changed, 'Expected signed group attribute'
        form.fields['SAMLResponse'] = base64.b64encode(xml.encode()).decode()
        assert client.post(form.action, data=form.fields).status_code == 400, 'Tampered assertion accepted'
        assert not client.get('http://127.0.0.1:8001/api/demo/auth/session').json()['result']['authenticated']
        print('Tampered signed group assertion rejected; no Django login created')


if __name__ == '__main__':
    main()
