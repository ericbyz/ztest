"""Network safety checks for live test execution."""

import ipaddress
import socket
from urllib.parse import urlparse


class UnsafeTargetError(ValueError):
    """Raised when a live execution target violates the allowlist policy."""


def validate_target(base_url: str, allow_hosts: list[str]) -> str:
    """Validate scheme, explicit host allowlist, and resolved IP addresses.

    Args:
        base_url: Candidate service base URL.
        allow_hosts: Hosts explicitly approved for this execution.

    Returns:
        The normalized base URL without a trailing slash.

    Raises:
        UnsafeTargetError: If the target is malformed, unapproved, or private.
    """

    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise UnsafeTargetError("仅允许有效的 HTTP/HTTPS 目标")

    host = parsed.hostname.lower()
    approved_hosts = {item.lower() for item in allow_hosts}
    if host not in approved_hosts:
        raise UnsafeTargetError(f"目标 {host} 不在本次执行 Allowlist 中")

    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(host, parsed.port)}
    except socket.gaierror as exc:
        raise UnsafeTargetError(f"无法解析目标域名 {host}") from exc

    for address in addresses:
        ip = ipaddress.ip_address(address)
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            raise UnsafeTargetError(f"目标 {address} 属于受保护网段")

    return base_url.rstrip("/")
