#!/usr/bin/env python3
"""Quick BioStar connectivity test — run on DO to verify network access."""

import sys
import json
import socket
import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def test_dns(host):
    """Step 1: DNS resolution."""
    print(f"\n1. DNS resolution for '{host}'...")
    try:
        ip = socket.gethostbyname(host)
        print(f"   OK — resolves to {ip}")
        return ip
    except socket.gaierror as e:
        print(f"   FAIL — {e}")
        return None


def test_tcp(host, port):
    """Step 2: TCP connectivity."""
    print(f"\n2. TCP connection to {host}:{port}...")
    try:
        sock = socket.create_connection((host, port), timeout=10)
        sock.close()
        print(f"   OK — port {port} is open")
        return True
    except (socket.timeout, ConnectionRefusedError, OSError) as e:
        print(f"   FAIL — {e}")
        return False


def test_https(host, port):
    """Step 3: HTTPS GET (no auth)."""
    url = f"https://{host}:{port}"
    print(f"\n3. HTTPS GET {url}...")
    try:
        resp = requests.get(url, timeout=15, verify=False)
        print(f"   OK — HTTP {resp.status_code} ({len(resp.content)} bytes)")
        return True
    except Exception as e:
        print(f"   FAIL — {e}")
        return False


def test_login(host, port, login_id, password):
    """Step 4: BioStar API login."""
    url = f"https://{host}:{port}/api/login"
    print(f"\n4. BioStar API login ({url})...")
    try:
        resp = requests.post(url, json={
            "User": {"login_id": login_id, "password": password}
        }, timeout=30, verify=False)

        print(f"   HTTP {resp.status_code}")
        body = resp.json()

        if resp.status_code == 200:
            session_id = resp.headers.get('bs-session-id', '(not in headers)')
            user_name = body.get('User', {}).get('name', 'Unknown')
            print(f"   OK — Logged in as '{user_name}'")
            print(f"   Session ID: {session_id[:20]}..." if len(str(session_id)) > 20 else f"   Session ID: {session_id}")
            return session_id if session_id != '(not in headers)' else None
        else:
            msg = body.get('Response', {}).get('message', 'Unknown error')
            print(f"   FAIL — {msg}")
            return None
    except Exception as e:
        print(f"   FAIL — {e}")
        return None


def test_users(host, port, session_id):
    """Step 5: Fetch users (verify session works)."""
    url = f"https://{host}:{port}/api/users?limit=1"
    print(f"\n5. Fetch users ({url})...")
    try:
        resp = requests.get(url, headers={'bs-session-id': session_id},
                           timeout=30, verify=False)
        body = resp.json()
        total = body.get('UserCollection', {}).get('total', '?')
        print(f"   OK — {total} total users in BioStar")
        return True
    except Exception as e:
        print(f"   FAIL — {e}")
        return False


def read_from_db():
    """Try to read BioStar credentials from the JARVIS database."""
    try:
        import os
        db_url = os.environ.get('DATABASE_URL')
        if not db_url:
            return None

        import psycopg2
        conn = psycopg2.connect(db_url)
        cur = conn.cursor()
        cur.execute("""
            SELECT config, credentials FROM connectors
            WHERE connector_type = 'biostar' LIMIT 1
        """)
        row = cur.fetchone()
        cur.close()
        conn.close()

        if not row:
            return None

        config = json.loads(row[0]) if isinstance(row[0], str) else row[0]
        creds = json.loads(row[1]) if isinstance(row[1], str) else row[1]
        return {
            'host': config.get('host'),
            'port': config.get('port', 443),
            'login_id': creds.get('login_id'),
            'password': creds.get('password'),
        }
    except Exception as e:
        print(f"   (Could not read from DB: {e})")
        return None


if __name__ == '__main__':
    print("=" * 60)
    print("BioStar 2 Connection Test")
    print("=" * 60)

    # Try DB first, then CLI args, then prompt
    creds = read_from_db()

    if creds:
        host = creds['host']
        port = creds['port']
        login_id = creds['login_id']
        password = creds['password']
        print(f"\nUsing credentials from database:")
        print(f"  Host: {host}:{port}")
        print(f"  User: {login_id}")
    elif len(sys.argv) >= 4:
        host = sys.argv[1]
        port = int(sys.argv[2]) if len(sys.argv) > 2 else 443
        login_id = sys.argv[3] if len(sys.argv) > 3 else None
        password = sys.argv[4] if len(sys.argv) > 4 else None
        print(f"\nUsing CLI args: {host}:{port} user={login_id}")
    else:
        print("\nUsage: python3 test_biostar_connection.py <host> <port> <login_id> <password>")
        print("Or set DATABASE_URL env var to read from JARVIS DB.")
        host = input("\nHost: ").strip()
        port = int(input("Port [443]: ").strip() or "443")
        login_id = input("Login ID: ").strip()
        password = input("Password: ").strip()

    # Run tests
    ip = test_dns(host)
    if not ip:
        print("\n*** DNS failed — check hostname or network config")
        sys.exit(1)

    tcp_ok = test_tcp(host, port)
    if not tcp_ok:
        print(f"\n*** TCP failed — port {port} not reachable from this server")
        print("    Check: firewall rules, VPN, security groups, BioStar server running")
        sys.exit(1)

    https_ok = test_https(host, port)
    if not https_ok:
        print("\n*** HTTPS failed — server not responding to HTTPS")
        sys.exit(1)

    if login_id and password:
        session_id = test_login(host, port, login_id, password)
        if not session_id:
            print("\n*** Login failed — check credentials")
            sys.exit(1)

        test_users(host, port, session_id)

    print("\n" + "=" * 60)
    print("ALL TESTS PASSED")
    print("=" * 60)
