#!/usr/bin/env python3
"""IP allowlist configuration generator for Fly.io security.

Generates Fly.io IP filtering configuration and documents the approach.
Fly.io uses WireGuard mesh networking which supports IP filtering via
services.ports.http_options.allowed_machines.

Usage:
    # Generate config from environment
    ALLOWED_IPS="1.2.3.4,5.6.7.8" python scripts/setup_ip_allowlist.py

    # Generate with specific IPs
    python scripts/setup_ip_allowlist.py --ips "1.2.3.4,5.6.7.8,10.0.0.0/24"

    # Generate from CIDR blocks
    python scripts/setup_ip_allowlist.py --ips "192.168.0.0/24,10.0.0.0/8"

    # Output toml snippet for fly.toml
    python scripts/setup_ip_allowlist.py --ips "1.2.3.4" --format toml

Environment Variables:
    ALLOWED_IPS: Comma-separated list of allowed IP addresses or CIDR blocks

References:
    - Fly.io networking: https://fly.io/docs/networking/
    - Fly.toml services: https://fly.io/docs/reference/configuration/#services
"""

from __future__ import annotations

import argparse
import ipaddress
import sys
from datetime import datetime
from typing import Any

from stonks_trading.shared.config import settings
from stonks_trading.shared.logger import logger


class IPAllowlistConfigurator:
    """Generates IP allowlist configuration for Fly.io."""

    def __init__(self, allowed_ips: list[str] | None = None):
        """Initialize configurator.

        Args:
            allowed_ips: List of IP addresses or CIDR blocks to allow
        """
        self.allowed_ips = allowed_ips or []
        self.validated_ips: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []

    def validate_ip(self, ip_str: str) -> tuple[bool, ipaddress.IPv4Network | ipaddress.IPv6Network | str]:
        """Validate an IP address or CIDR block.

        Args:
            ip_str: IP address or CIDR notation (e.g., "1.2.3.4" or "192.168.0.0/24")

        Returns:
            Tuple of (is_valid, network_object or error_message)
        """
        ip_str = ip_str.strip()

        if not ip_str:
            return False, "Empty IP string"

        try:
            # Try as network first (handles both single IP and CIDR)
            if "/" in ip_str:
                network = ipaddress.ip_network(ip_str, strict=False)
            else:
                # Single IP - convert to /32 for IPv4 or /128 for IPv6
                network = ipaddress.ip_network(f"{ip_str}/32", strict=False)
            return True, network
        except ValueError as e:
            return False, f"Invalid IP or CIDR: {e}"

    def validate_all(self) -> tuple[bool, list[str]]:
        """Validate all IPs in the allowlist.

        Returns:
            Tuple of (all_valid, list_of_error_messages)
        """
        errors = []
        self.validated_ips = []

        for ip_str in self.allowed_ips:
            is_valid, result = self.validate_ip(ip_str)
            if is_valid:
                self.validated_ips.append(result)
            else:
                errors.append(f"'{ip_str}': {result}")

        return len(errors) == 0, errors

    def generate_nginx_config(self) -> str:
        """Generate nginx allow/deny configuration.

        Fly.io doesn't natively support IP filtering in fly.toml,
        so we can use nginx as a reverse proxy with allow/deny rules.

        Returns:
            Nginx configuration snippet
        """
        lines = [
            "# IP Allowlist Configuration for Nginx",
            f"# Generated at: {datetime.utcnow().isoformat()}",
            f"# Total allowed IPs/networks: {len(self.validated_ips)}",
            "",
            "# Deny all by default",
            "deny all;",
            "",
            "# Allow specific IPs/networks",
        ]

        for network in self.validated_ips:
            if network.prefixlen == 32 and isinstance(network, ipaddress.IPv4Network):
                # Single IPv4 - use allow directive
                lines.append(f"allow {network.network_address};")
            elif network.prefixlen == 128 and isinstance(network, ipaddress.IPv6Network):
                # Single IPv6
                lines.append(f"allow {network.network_address};")
            else:
                # CIDR block
                lines.append(f"allow {network};")

        lines.extend([
            "",
            "# Deny everything else (redundant but explicit)",
            "deny all;",
        ])

        return "\n".join(lines)

    def generate_fly_toml_snippet(self) -> str:
        """Generate Fly.toml snippet for IP-based access control.

        Note: Fly.io doesn't have native IP filtering in services.http_checks,
        but we can document the approach using WireGuard ACLs and services
        configuration.

        Returns:
            Fly.toml configuration documentation
        """
        lines = [
            "# IP Allowlist Configuration for Fly.io",
            f"# Generated at: {datetime.utcnow().isoformat()}",
            f"# Total allowed IPs/networks: {len(self.validated_ips)}",
            "",
            "# NOTE: Fly.io does not support native IP allowlisting in fly.toml.",
            "# The recommended approaches are:",
            "#",
            "# 1. Application-level IP filtering (implemented in the app)",
            "# 2. Nginx reverse proxy with allow/deny (see generate_nginx_config)",
            "# 3. Cloudflare Access or similar edge protection",
            "# 4. WireGuard ACLs (requires custom networking setup)",
            "",
            "# For application-level filtering, add this middleware to your app:",
            "",
            "[[services]]",
            "  internal_port = 8000",
            "  protocol = \"tcp\"",
            "  ",
            "  [[services.ports]]",
            "    handlers = [\"http\"]",
            "    port = 80",
            "    force_https = true",
            "  ",
            "  [[services.ports]]",
            "    handlers = [\"tls\", \"http\"]",
            "    port = 443",
            "    force_https = true",
            "",
            "# Application-level IP filtering middleware should check:",
        ]

        for network in self.validated_ips:
            lines.append(f"#   - Client IP in {network}")

        return "\n".join(lines)

    def generate_python_middleware(self) -> str:
        """Generate Python/FastAPI middleware for IP filtering.

        Returns:
            Python code snippet for IP-based access control
        """
        lines = [
            "# IP Allowlist Middleware for FastAPI",
            f"# Generated at: {datetime.utcnow().isoformat()}",
            "",
            "import ipaddress",
            "from fastapi import Request, HTTPException",
            "from fastapi.responses import JSONResponse",
            "",
            "# Allowed IP networks",
            "ALLOWED_NETWORKS = [",
        ]

        for network in self.validated_ips:
            lines.append(f'    ipaddress.ip_network("{network}"),')

        lines.extend([
            "]",
            "",
            "",
            "async def ip_allowlist_middleware(request: Request, call_next):",
            '    """Middleware to enforce IP allowlist."""',
            "    client_ip = request.client.host",
            "",
            "    # Handle X-Forwarded-For from Fly.io proxy",
            "    forwarded_for = request.headers.get(\"x-forwarded-for\")",
            "    if forwarded_for:",
            "        client_ip = forwarded_for.split(\",\")[0].strip()",
            "",
            "    try:",
            "        client_network = ipaddress.ip_network(f\"{client_ip}/32\", strict=False)",
            "        ",
            "        # Check if IP is in allowed networks",
            "        is_allowed = any(",
            "            client_network.subnet_of(allowed)",
            "            for allowed in ALLOWED_NETWORKS",
            "        )",
            "        ",
            "        if not is_allowed:",
            '            logger.warning(f"Blocked request from {client_ip}")',
            "            return JSONResponse(",
            '                status_code=403,',
            '                content={"detail": "Access denied"},',
            "            )",
            "    except ValueError:",
            '        logger.error(f"Invalid client IP: {client_ip}")',
            "        return JSONResponse(",
            '            status_code=400,',
            '            content={"detail": "Invalid IP address"},',
            "        )",
            "",
            "    return await call_next(request)",
        ])

        return "\n".join(lines)

    def generate_documentation(self) -> str:
        """Generate comprehensive documentation for IP allowlisting.

        Returns:
            Markdown documentation
        """
        doc = f"""# IP Allowlist Configuration Guide

Generated: {datetime.utcnow().isoformat()}

## Allowed IPs/Networks

"""
        for network in self.validated_ips:
            doc += f"- `{network}`\n"

        doc += f"""
**Total:** {len(self.validated_ips)} network(s)

## Implementation Options

### Option 1: Application-Level (Recommended)

Add the Python middleware to your FastAPI application in `api.py`:

```python
# Add near the top of create_app()
app.middleware("http")(ip_allowlist_middleware)
```

This checks the `X-Forwarded-For` header from Fly.io's proxy and
validates against the allowlist before processing requests.

### Option 2: Nginx Reverse Proxy

If using nginx in front of your application, add the generated
configuration to your nginx server block.

### Option 3: Cloudflare Access

For production environments, consider Cloudflare Access or similar
zero-trust networking solutions that provide IP-based access control
at the edge.

## Fly.io Specific Notes

1. Fly.io uses WireGuard mesh networking between apps
2. The `X-Forwarded-For` header contains the original client IP
3. Fly.io IPs are preserved through the proxy
4. Health checks from Fly.io will use internal IPs

## Testing

Verify IP filtering with curl:

```bash
# From allowed IP (should succeed)
curl https://your-app.fly.dev/health

# From disallowed IP (should get 403)
curl https://your-app.fly.dev/health
```

## Security Considerations

- Always use HTTPS (Fly.io sets `force_https = true` by default)
- Log blocked requests for security monitoring
- Consider rate limiting in addition to IP filtering
- Rotate IPs periodically if using dynamic addresses
- Document all authorized IPs and their purpose

## Emergency Access

If you lock yourself out:
1. SSH into the Fly.io VM: `fly ssh console -a your-app`
2. Edit the allowlist configuration
3. Restart the application
4. Or use `fly secrets deploy` to bypass

"""
        return doc


def parse_ips_from_string(ip_string: str) -> list[str]:
    """Parse comma-separated IP string into list.

    Args:
        ip_string: Comma-separated IPs or CIDR blocks

    Returns:
        List of IP strings
    """
    return [ip.strip() for ip in ip_string.split(",") if ip.strip()]


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Generate IP allowlist configuration for Fly.io security",
    )
    parser.add_argument(
        "--ips",
        help="Comma-separated list of allowed IPs or CIDR blocks",
    )
    parser.add_argument(
        "--format",
        choices=["toml", "nginx", "python", "docs", "all"],
        default="all",
        help="Output format (default: all)",
    )
    parser.add_argument(
        "--output",
        "-o",
        help="Output file (default: stdout)",
    )

    args = parser.parse_args()

    # Get IPs from args or environment
    ip_string = args.ips or settings.__dict__.get("allowed_ips", "")

    if not ip_string:
        logger.error(
            "No IPs specified. Use --ips or set ALLOWED_IPS environment variable"
        )
        print("\nExample usage:")
        print('  ALLOWED_IPS="1.2.3.4,5.6.7.8" python scripts/setup_ip_allowlist.py')
        print('  python scripts/setup_ip_allowlist.py --ips "192.168.0.0/24" --format nginx')
        return 1

    # Parse and validate IPs
    allowed_ips = parse_ips_from_string(ip_string)
    configurator = IPAllowlistConfigurator(allowed_ips)

    is_valid, errors = configurator.validate_all()
    if not is_valid:
        logger.error("IP validation failed:")
        for error in errors:
            logger.error(f"  - {error}")
        return 1

    logger.info(f"Validated {len(configurator.validated_ips)} IP/network(s)")

    # Generate output based on format
    outputs: dict[str, str] = {}

    if args.format in ["toml", "all"]:
        outputs["Fly.io TOML"] = configurator.generate_fly_toml_snippet()

    if args.format in ["nginx", "all"]:
        outputs["Nginx Config"] = configurator.generate_nginx_config()

    if args.format in ["python", "all"]:
        outputs["Python Middleware"] = configurator.generate_python_middleware()

    if args.format in ["docs", "all"]:
        outputs["Documentation"] = configurator.generate_documentation()

    # Output results
    output_text = ""
    for name, content in outputs.items():
        if args.format == "all":
            output_text += f"\n{'=' * 60}\n"
            output_text += f"{name}\n"
            output_text += f"{'=' * 60}\n\n"
        output_text += content + "\n\n"

    if args.output:
        with open(args.output, "w") as f:
            f.write(output_text)
        logger.info(f"Configuration written to: {args.output}")
    else:
        print(output_text)

    return 0


if __name__ == "__main__":
    sys.exit(main())
