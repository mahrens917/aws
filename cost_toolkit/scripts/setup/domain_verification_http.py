"""HTTP and DNS verification helpers for domain checks."""

import socket
from dataclasses import dataclass
from typing import Mapping
from urllib import error as urllib_error
from urllib import request as urllib_request

# HTTP status codes
HTTP_STATUS_MOVED_PERMANENTLY = 301
HTTP_STATUS_OK = 200


@dataclass
class HttpResult:
    """Minimal HTTP response representation."""

    status_code: int
    headers: Mapping[str, str]


class HttpRequestError(RuntimeError):
    """Raised when HTTP retrieval fails."""


class _NoRedirectHandler(urllib_request.HTTPRedirectHandler):
    """Prevent automatic redirect following so we can inspect status codes."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _http_get(url: str, *, allow_redirects: bool, timeout: int) -> HttpResult:
    """Perform an HTTP GET with optional redirect following."""
    handlers = [] if allow_redirects else [_NoRedirectHandler]
    opener = urllib_request.build_opener(*(handler() for handler in handlers))
    try:
        response = opener.open(urllib_request.Request(url, method="GET"), timeout=timeout)
        status = getattr(response, "status", HTTP_STATUS_OK)
        headers = dict(response.headers.items()) if response.headers else {}
        return HttpResult(status_code=status, headers=headers)
    except urllib_error.HTTPError as exc:
        headers = dict(exc.headers.items()) if exc.headers else {}
        return HttpResult(status_code=exc.code, headers=headers)
    except urllib_error.URLError as exc:
        raise HttpRequestError(str(exc)) from exc


def verify_dns_resolution(domain):
    """Test DNS resolution for the domain"""
    print(f"🔍 Testing DNS resolution for {domain}")

    try:
        # Test A record resolution
        ip_address = socket.gethostbyname(domain)
        print(f"  ✅ {domain} resolves to: {ip_address}")

        # Test www subdomain
        www_domain = f"www.{domain}"
        www_ip = socket.gethostbyname(www_domain)
        print(f"  ✅ {www_domain} resolves to: {www_ip}")

    except (socket.gaierror, OSError) as e:
        print(f"  ❌ DNS resolution failed: {e}")
        return False, None

    return True, ip_address


def verify_http_connectivity(domain):
    """Test HTTP connectivity and redirects"""
    print(f"\n🌐 Testing HTTP connectivity for {domain}")

    try:
        # Test HTTP (should redirect to HTTPS)
        http_url = f"http://{domain}"
        response = _http_get(http_url, allow_redirects=False, timeout=10)

        location_header = response.headers.get("Location")
        if response.status_code == HTTP_STATUS_MOVED_PERMANENTLY and location_header and "https://" in location_header:
            print(f"  ✅ HTTP redirects to HTTPS ({HTTP_STATUS_MOVED_PERMANENTLY}): " f"{response.headers['Location']}")
        else:
            print(f"  ⚠️  HTTP response: {response.status_code}")

    except HttpRequestError as e:
        print(f"  ❌ HTTP test failed: {e}")
        return False

    return True


def verify_https_connectivity(domain):
    """Test HTTPS connectivity and SSL certificate"""
    print(f"\n🔒 Testing HTTPS connectivity for {domain}")

    try:
        # Test HTTPS connectivity
        https_url = f"https://{domain}"
        response = _http_get(https_url, allow_redirects=True, timeout=10)

        if response.status_code == HTTP_STATUS_OK:
            print(f"  ✅ HTTPS connection successful ({HTTP_STATUS_OK})")
            content_type = response.headers.get("Content-Type")
            print(f"  ✅ Content-Type: {content_type}")

            # Check if it's served by Cloudflare (Canva uses Cloudflare)
            server = response.headers.get("Server")
            if server and "cloudflare" in server.lower():
                print("  ✅ Served by Cloudflare (Canva infrastructure)")

            return True

    except HttpRequestError as e:
        print(f"  ❌ HTTPS test failed: {e}")
        return False

    print(f"  ⚠️  HTTPS response: {response.status_code}")
    return False


if __name__ == "__main__":  # pragma: no cover - script entry point
    pass
