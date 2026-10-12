"""CarBackground.ai shared constants + SSRF guard.

`_validate_url` guards every server-side download against SSRF (blocks the
cloud-metadata endpoint 169.254.169.254 and RFC1918 pivots): only http(s) to
a publicly-routable host is allowed. `BROWSER_UA` is sent on every outbound
request to CarBackground to dodge Cloudflare's Error-1010 bot block.

The service class (orchestration: generate + store enhanced photo) is added
in Task 4 — this file only holds the constants and guards needed by Task 3's
client.
"""
import ipaddress
import socket
from urllib.parse import urlparse

CONNECTOR_TYPE = 'carbackground'
DOWNLOAD_TIMEOUT = 60
MAX_IMAGE_BYTES = 50 * 1024 * 1024
BROWSER_UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
              '(KHTML, like Gecko) Chrome/129.0 Safari/537.36')
_ALLOWED_SCHEMES = ('http', 'https')


class CarBackgroundError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.message = message
        self.status = status


def _validate_url(url):
    p = urlparse(url)
    if p.scheme not in _ALLOWED_SCHEMES:
        raise CarBackgroundError(f'URL scheme not allowed: {url}', 400)
    host = (p.hostname or '').rstrip('.').lower()
    if not host:
        raise CarBackgroundError(f'URL has no host: {url}', 400)
    try:
        infos = socket.getaddrinfo(host, p.port or None)
    except socket.gaierror as e:
        raise CarBackgroundError(f'Cannot resolve host {host}: {e}', 400)
    for *_u, sockaddr in infos:
        ip = ipaddress.ip_address(sockaddr[0])
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
            raise CarBackgroundError(f'Blocked non-public host {host} ({ip})', 400)
