#!/usr/bin/env python3
"""Probe the Japanese MyNISSAN backend for a new (ZE2) Leaf.

The new Leaf signs in with a NISSAN ID (id.nissan.io) instead of the old
NissanConnect member ID. This script does that login the way the MyNISSAN
app does (OAuth + PKCE), swaps the NISSAN ID token for a backend token, then
asks each vehicle endpoint the app knows about for its data. The answers are
written to probe_result.json with the VIN, location, tokens and personal data
redacted, so they can be shared to build the integration.

Only GET requests are sent to the car endpoints: nothing on the car changes
and the car is not woken.

Usage (from a folder outside the repo, which keeps the saved login and the
output out of it):
    .venv/bin/python ha-mynissan-jp/nissan_jp_probe.py
"""

import argparse
import base64
import hashlib
import json
import os
import re
import secrets
import sys
import time
from urllib.parse import parse_qs, urlencode, urlparse

import requests

CIAM = 'https://id.nissan.io/9d5118a8-dc9c-4e8f-8924-4781cf369f41/login/'
CLIENT_ID = '4db8eab8-8088-4b92-9c14-9bc89fa49c2a'
REDIRECT_URI = 'ncx://ciam.prd/login'
# Kept in the folder the script is run from, like probe_result.json
TOKEN_FILE = '.nissan_token.json'

BFF = 'https://nc-app-bff-prod.apps.jp.kamereon.io/nc-app-bff/'
APP_ID = 'jp.co.nissan.nissanconnect.ncx'
JSONAPI = {'Content-Type': 'application/vnd.api+json'}

# cars/{vin}/<resource> under each of these bases
BASES = {
    'vehicle-info/v1': BFF + 'nissan/vehicle-info/v1/cars/',
    'vehicle-info/v2': BFF + 'nissan/vehicle-info/v2/cars/',
    'car-adapter/v1': BFF + 'alliance/car-adapter/v1/cars/',
    'car-adapter/v2': BFF + 'alliance/car-adapter/v2/cars/',
}
RESOURCES = [
    'battery-status', 'cockpit', 'location', 'hvac-status', 'lock-status',
    'health-status', 'pressure', 'charging-settings', 'hvac-settings',
    'res-state', 'trip-history',
]
OTHER = {
    'config/details': BFF + 'nissan/config/v1/cars/{vin}/details',
    'config/color-info': BFF + 'nissan/config/v1/cars/{vin}/color-info',
    'account/cars/entitlements': BFF + 'nissan/account/v1/cars/{vin}/entitlements',
    'account/cars/contract': BFF + 'nissan/account/v1/cars/{vin}/contract',
}

SENSITIVE_KEYS = re.compile(
    r'(token|password|email|mail|phone|name|address|vin|userid|user_id|'
    r'latitude|longitude|registration|plate|birth|zip|postal|nuid|sub$)',
    re.IGNORECASE)


class Redactor:
    def __init__(self):
        self.secrets = {}

    def add(self, value, label):
        if value and isinstance(value, str) and len(value) > 3:
            self.secrets[value] = label

    def __call__(self, obj, key=''):
        if isinstance(obj, dict):
            return {k: self(v, k) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self(v, key) for v in obj]
        sensitive = SENSITIVE_KEYS.search(key) and 'model' not in key.lower()
        if isinstance(obj, str):
            if sensitive:
                return '<redacted>'
            for secret, label in self.secrets.items():
                obj = obj.replace(secret, label)
            return obj
        if isinstance(obj, (int, float)) and not isinstance(obj, bool) and sensitive:
            return '<redacted>'
        return obj


def body_of(resp):
    try:
        return resp.json()
    except ValueError:
        return resp.text[:2000]


def ciam_login():
    """Browser login with PKCE; returns the NISSAN ID token response."""
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
    state = secrets.token_urlsafe(16)
    url = CIAM + 'authorize?' + urlencode({
        'client_id': CLIENT_ID,
        'response_type': 'code',
        'redirect_uri': REDIRECT_URI,
        'scope': 'openid',
        'state': state,
        'nonce': secrets.token_urlsafe(16),
        'code_challenge': challenge,
        'code_challenge_method': 'S256',
        'ui_locales': 'ja',
    })
    print(__doc__.split('Usage')[0].strip().splitlines()[0])
    print('\n1. Open this link in Chrome on your Mac (not on the phone):\n')
    print(url)
    print('\n2. Before logging in, open DevTools (Cmd+Option+I) > Network tab.')
    print('3. Log in with your NISSAN ID and enter the access code from your email.')
    print('4. The page will then seem to do nothing. In the Network tab, find the')
    print('   last request (status 302, or a red one starting with ncx://).')
    print('   Copy the full ncx://ciam.prd/login?code=... address from its')
    print('   "Location" header or the request URL.\n')
    redirect = input('Paste the ncx://... address here: ').strip()
    query = parse_qs(urlparse(redirect).query)
    if 'code' not in query:
        sys.exit(f'No code found in that address: {query or redirect[:80]}')
    if query.get('state', [None])[0] != state:
        sys.exit('That address is from a different login attempt; run the script again.')

    resp = requests.post(CIAM + 'token', data={
        'grant_type': 'authorization_code',
        'client_id': CLIENT_ID,
        'code': query['code'][0],
        'redirect_uri': REDIRECT_URI,
        'code_verifier': verifier,
    })
    return resp.status_code, body_of(resp)


def ciam_refresh():
    """Log in silently with a saved refresh token; None if there isn't one."""
    try:
        with open(TOKEN_FILE, encoding='utf-8') as f:
            refresh_token = json.load(f)['refresh_token']
    except (OSError, ValueError, KeyError):
        return None
    resp = requests.post(CIAM + 'token', data={
        'grant_type': 'refresh_token',
        'client_id': CLIENT_ID,
        'refresh_token': refresh_token,
    })
    body = body_of(resp)
    if resp.status_code >= 400 or not isinstance(body, dict) or 'access_token' not in body:
        print('Saved login has expired, logging in again.')
        return None
    print('Logged in with the saved NISSAN ID session.')
    return resp.status_code, body


def save_refresh_token(ciam):
    if not ciam.get('refresh_token'):
        return
    fd = os.open(TOKEN_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        json.dump({'refresh_token': ciam['refresh_token']}, f)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', default='probe_result.json')
    args = parser.parse_args()

    redact = Redactor()
    result = {'ciam': None, 'exchange': [], 'account': {}, 'vehicles': {}}

    status, ciam = ciam_refresh() or ciam_login()
    if isinstance(ciam, dict):
        save_refresh_token(ciam)
    result['ciam'] = {'status': status,
                      'keys': sorted(ciam) if isinstance(ciam, dict) else None,
                      'scope': ciam.get('scope') if isinstance(ciam, dict) else None,
                      'expires_in': ciam.get('expires_in') if isinstance(ciam, dict) else None}
    if status >= 400 or not isinstance(ciam, dict) or 'access_token' not in ciam:
        result['ciam']['body'] = ciam
        print('NISSAN ID token request failed:', status)
        return finish(result, redact, args.out)
    for k in ('access_token', 'id_token', 'refresh_token'):
        redact.add(ciam.get(k), f'<ciam_{k}>')
    print('NISSAN ID login OK, exchanging token...')

    s = requests.Session()
    s.headers.update({'User-Agent': 'okhttp/4.12.0', 'x-app-id': APP_ID})

    # The envelope is {"data": {"type": "exchangeToken", "id": ..., "attributes":
    # {"token": ...}}}; which token and which id the server wants is not yet
    # known, so try the likely combinations until one is accepted.
    token = None
    for which in ('access_token', 'id_token'):
        for data_id in ('1', CLIENT_ID, APP_ID):
            payload = {'data': {'type': 'exchangeToken', 'id': data_id,
                                'attributes': {'token': ciam[which]}}}
            r = s.post(BFF + 'nissan/account/v1/exchange-token', json=payload)
            body = body_of(r)
            result['exchange'].append({'which': which, 'data_id': data_id,
                                       'status': r.status_code, 'body': body})
            attrs = body.get('data', {}).get('attributes', {}) if isinstance(body, dict) else {}
            if r.status_code < 300 and attrs.get('access_token'):
                token = attrs['access_token']
                break
        if token:
            break
    if not token:
        print('Token exchange failed; see the output file.')
        return finish(result, redact, args.out)
    redact.add(token, '<token>')
    s.headers['Authorization'] = 'Bearer ' + token
    print('Backend login OK, reading account...')

    def get(url, **kw):
        r = s.get(url, **kw)
        return {'status': r.status_code, 'body': body_of(r)}

    token_info = get(BFF + 'nissan/account/v1/token-info')
    result['account']['token-info'] = token_info
    user = get(BFF + 'alliance/user-adapter/v1/users/current')
    result['account']['users/current'] = user
    user_id = user['body'].get('userId') if isinstance(user['body'], dict) else None
    redact.add(user_id, '<user_id>')

    try:
        vehicles = token_info['body']['data']['attributes']['vehicles']
    except (KeyError, TypeError):
        vehicles = []
    if not vehicles:
        print('No vehicles found in token-info; see the output file.')

    for n, vehicle in enumerate(vehicles, 1):
        vin = vehicle.get('vin', '')
        label = f'<vin{n}>'
        redact.add(vin, label)
        redact.add(vin.upper(), label)
        print(f'Probing vehicle {n}...')
        out = result['vehicles'][label] = {}
        for name, url in OTHER.items():
            out[name] = get(url.format(vin=vin))
        for base_name, base in BASES.items():
            for res in RESOURCES:
                params = None
                if res == 'trip-history':
                    params = {'type': 'month', 'start': time.strftime('%Y%m01'),
                              'end': time.strftime('%Y%m%d')}
                out[f'{base_name}/{res}'] = get(f'{base}{vin}/{res}',
                                                headers=JSONAPI, params=params)

    finish(result, redact, args.out)


def ok(r):
    return r['status'] < 300 and not (isinstance(r['body'], dict) and 'errors' in r['body'])


def finish(result, redact, path):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(redact(result), f, ensure_ascii=False, indent=2)
    print(f'\nWrote {path}. Summary:')
    for e in result['exchange']:
        print(f'  {"OK " if e["status"] < 300 else "-- "}{e["status"]}  exchange-token '
              f'({e["which"]}, id={e["data_id"]})')
    for name, r in result['account'].items():
        print(f'  {"OK " if ok(r) else "-- "}{r["status"]}  {name}')
    for endpoints in result['vehicles'].values():
        for name, r in endpoints.items():
            print(f'  {"OK " if ok(r) else "-- "}{r["status"]}  {name}')
    print('\nPlease look over the file before sharing it.')


if __name__ == '__main__':
    sys.exit(main())
