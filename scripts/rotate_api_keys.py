#!/usr/bin/env python3
"""API key rotation script for exchange credentials.

Validates new keys against exchange test endpoints, updates Fly.io secrets,
triggers bluegreen deploy, and verifies health endpoint after deployment.

Usage:
    # Rotate Binance keys
    python scripts/rotate_api_keys.py --exchange binance --api-key NEW_KEY --api-secret NEW_SECRET

    # Rotate using environment variables
    BINANCE_API_KEY=new_key BINANCE_API_SECRET=new_secret python scripts/rotate_api_keys.py --exchange binance

    # Validate only (no deploy)
    python scripts/rotate_api_keys.py --exchange binance --validate-only

Environment Variables:
    BINANCE_API_KEY / BINANCE_API_SECRET: New Binance credentials
    BITSO_API_KEY / BITSO_API_SECRET: New Bitso credentials
    DISCORD_WEBHOOK_URL: For deployment notifications
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import hmac
import json
import subprocess
import sys
import time
import urllib.parse
from datetime import datetime
from typing import Any

import httpx

from stonks_trading.shared.config import settings
from stonks_trading.shared.logger import logger
from stonks_trading.shared.notifications import DiscordNotifier


class KeyValidator:
    """Validates exchange API keys against test endpoints."""

    def __init__(self):
        self.client = httpx.AsyncClient(timeout=30.0)

    async def validate_binance(self, api_key: str, api_secret: str) -> tuple[bool, str]:
        """Validate Binance API keys.

        Args:
            api_key: Binance API key
            api_secret: Binance API secret

        Returns:
            Tuple of (is_valid, message)
        """
        base_url = "https://api.binance.com"
        timestamp = int(time.time() * 1000)

        # Create signature for account endpoint
        query_string = f"timestamp={timestamp}"
        signature = hmac.new(
            api_secret.encode("utf-8"),
            query_string.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()

        url = f"{base_url}/api/v3/account?{query_string}&signature={signature}"
        headers = {"X-MBX-APIKEY": api_key}

        try:
            response = await self.client.get(url, headers=headers)

            if response.status_code == 200:
                data = response.json()
                # Check if we can read account info
                if "balances" in data:
                    return True, f"Valid key. Account can trade: {data.get('canTrade', False)}"
                return True, "Valid key"
            elif response.status_code == 401:
                error_msg = response.json().get("msg", "Invalid credentials")
                return False, f"Authentication failed: {error_msg}"
            else:
                return False, f"HTTP {response.status_code}: {response.text}"

        except httpx.TimeoutException:
            return False, "Timeout connecting to Binance"
        except Exception as e:
            return False, f"Error: {str(e)}"

    async def validate_bitso(self, api_key: str, api_secret: str) -> tuple[bool, str]:
        """Validate Bitso API keys.

        Args:
            api_key: Bitso API key
            api_secret: Bitso API secret

        Returns:
            Tuple of (is_valid, message)
        """
        base_url = "https://api.bitso.com/v3"

        # Bitso uses HMAC auth with specific header format
        timestamp = str(int(time.time()))
        http_method = "GET"
        request_path = "/balance/"

        # Create auth string
        auth_data = f"{timestamp}{http_method}{request_path}"
        signature = hmac.new(
            api_secret.encode("utf-8"),
            auth_data.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()

        headers = {
            "Authorization": f"Bitso {api_key}:{signature}",
            "Bitso-API-Auth": signature,
        }

        try:
            response = await self.client.get(
                f"{base_url}/balance/",
                headers=headers
            )

            if response.status_code == 200:
                data = response.json()
                if data.get("success"):
                    return True, "Valid key"
                return False, f"API error: {data.get('error', {}).get('message', 'Unknown')}"
            elif response.status_code == 401:
                return False, "Invalid credentials"
            else:
                return False, f"HTTP {response.status_code}: {response.text}"

        except httpx.TimeoutException:
            return False, "Timeout connecting to Bitso"
        except Exception as e:
            return False, f"Error: {str(e)}"

    async def close(self) -> None:
        await self.client.aclose()


class FlyDeployer:
    """Handles Fly.io secret updates and deployments."""

    def __init__(self, app_name: str = "stonks-trading-api"):
        self.app_name = app_name

    def _run_fly_command(
        self,
        args: list[str],
        capture_output: bool = True,
    ) -> tuple[bool, str]:
        """Run a flyctl command.

        Args:
            args: Command arguments
            capture_output: Whether to capture output

        Returns:
            Tuple of (success, output)
        """
        cmd = ["flyctl"] + args
        try:
            result = subprocess.run(
                cmd,
                capture_output=capture_output,
                text=True,
                check=True,
            )
            return True, result.stdout
        except subprocess.CalledProcessError as e:
            return False, f"Command failed: {e.stderr}"
        except FileNotFoundError:
            return False, "flyctl not found. Install with: brew install flyctl"

    def update_secrets(self, secrets: dict[str, str]) -> tuple[bool, str]:
        """Update Fly.io secrets.

        Args:
            secrets: Dictionary of secret name -> value

        Returns:
            Tuple of (success, message)
        """
        if not secrets:
            return True, "No secrets to update"

        # Build secrets in KEY=VALUE format
        secret_args = [f"{k}={v}" for k, v in secrets.items()]

        args = [
            "secrets",
            "set",
            "-a", self.app_name,
            *secret_args,
        ]

        success, output = self._run_fly_command(args)
        if success:
            return True, f"Updated {len(secrets)} secret(s)"
        return False, output

    def deploy(self, config_path: str = "infra/fly.api.toml") -> tuple[bool, str]:
        """Trigger bluegreen deployment.

        Args:
            config_path: Path to fly.toml config

        Returns:
            Tuple of (success, message)
        """
        args = [
            "deploy",
            "-c", config_path,
            "--strategy", "bluegreen",
        ]

        success, output = self._run_fly_command(args, capture_output=True)
        if success:
            return True, "Bluegreen deploy initiated"
        return False, output

    def get_app_status(self) -> tuple[bool, dict[str, Any] | str]:
        """Get app status from Fly.io.

        Returns:
            Tuple of (success, status_dict or error_message)
        """
        args = ["status", "-a", self.app_name, "--json"]
        success, output = self._run_fly_command(args)

        if not success:
            return False, output

        try:
            data = json.loads(output)
            return True, data
        except json.JSONDecodeError as e:
            return False, f"Failed to parse status: {e}"


class HealthChecker:
    """Verifies API health after deployment."""

    def __init__(self, base_url: str = "https://stonks-trading-api.fly.dev"):
        self.base_url = base_url
        self.client = httpx.AsyncClient(timeout=10.0)

    async def check_ready(self) -> tuple[bool, str]:
        """Check if API is ready.

        Returns:
            Tuple of (is_healthy, message)
        """
        try:
            response = await self.client.get(f"{self.base_url}/health/ready")
            if response.status_code == 200:
                return True, "API is healthy"
            return False, f"HTTP {response.status_code}"
        except httpx.TimeoutException:
            return False, "Timeout"
        except Exception as e:
            return False, str(e)

    async def check_full_health(self) -> tuple[bool, dict[str, Any] | str]:
        """Check full health endpoint.

        Returns:
            Tuple of (is_healthy, health_data or error_message)
        """
        try:
            response = await self.client.get(f"{self.base_url}/health")
            if response.status_code == 200:
                return True, response.json()
            return False, f"HTTP {response.status_code}"
        except Exception as e:
            return False, str(e)

    async def close(self) -> None:
        await self.client.aclose()


class KeyRotationOrchestrator:
    """Orchestrates the complete key rotation workflow."""

    def __init__(self):
        self.validator = KeyValidator()
        self.deployer = FlyDeployer()
        self.health_checker = HealthChecker()
        self.notifier = DiscordNotifier(settings.discord_webhook_url)

    async def rotate(
        self,
        exchange: str,
        api_key: str,
        api_secret: str,
        validate_only: bool = False,
        skip_deploy: bool = False,
    ) -> bool:
        """Execute key rotation workflow.

        Args:
            exchange: Exchange name (binance, bitso)
            api_key: New API key
            api_secret: New API secret
            validate_only: Only validate, don't update
            skip_deploy: Validate and update secrets, but don't deploy

        Returns:
            True if successful
        """
        version = "0.1.0"  # Match pyproject.toml
        environment = "production"

        # Step 1: Validate keys
        logger.info(f"Validating {exchange} API keys...")

        if exchange == "binance":
            is_valid, message = await self.validator.validate_binance(api_key, api_secret)
        elif exchange == "bitso":
            is_valid, message = await self.validator.validate_bitso(api_key, api_secret)
        else:
            logger.error(f"Unknown exchange: {exchange}")
            return False

        if not is_valid:
            logger.error(f"Key validation failed: {message}")
            await self.notifier.send_alert_notification(
                alert_name="API Key Rotation Failed",
                severity="critical",
                description=f"Key validation failed for {exchange}: {message}",
                labels={"exchange": exchange, "step": "validation"},
            )
            return False

        logger.info(f"Key validation passed: {message}")

        if validate_only:
            logger.info("Validation only mode - skipping deployment")
            return True

        # Step 2: Send deploy started notification
        await self.notifier.send_deploy_notification(
            version=version,
            environment=environment,
            status="started",
        )

        # Step 3: Update Fly.io secrets
        if exchange == "binance":
            secrets = {
                "BINANCE_API_KEY": api_key,
                "BINANCE_API_SECRET": api_secret,
            }
        else:  # bitso
            secrets = {
                "BITSO_API_KEY": api_key,
                "BITSO_API_SECRET": api_secret,
            }

        logger.info("Updating Fly.io secrets...")
        success, message = self.deployer.update_secrets(secrets)
        if not success:
            logger.error(f"Failed to update secrets: {message}")
            await self.notifier.send_deploy_notification(
                version=version,
                environment=environment,
                status="failed",
            )
            return False
        logger.info(f"Secrets updated: {message}")

        if skip_deploy:
            logger.info("Deploy skipped - secrets updated only")
            await self.notifier.send_deploy_notification(
                version=version,
                environment=environment,
                status="complete",
            )
            return True

        # Step 4: Deploy with bluegreen strategy
        logger.info("Initiating bluegreen deployment...")
        success, message = self.deployer.deploy()
        if not success:
            logger.error(f"Deploy failed: {message}")
            await self.notifier.send_deploy_notification(
                version=version,
                environment=environment,
                status="failed",
            )
            return False
        logger.info("Deploy initiated")

        # Step 5: Wait and verify health
        logger.info("Waiting 30 seconds for deployment...")
        await asyncio.sleep(30)

        logger.info("Verifying health endpoint...")
        is_healthy, health_msg = await self.health_checker.check_ready()

        if is_healthy:
            logger.info(f"Health check passed: {health_msg}")
            await self.notifier.send_deploy_notification(
                version=version,
                environment=environment,
                status="complete",
            )
            logger.info("Key rotation completed successfully")
            return True
        else:
            logger.error(f"Health check failed: {health_msg}")
            await self.notifier.send_alert_notification(
                alert_name="Deploy Health Check Failed",
                severity="critical",
                description=f"Deployment succeeded but health check failed: {health_msg}",
                labels={"exchange": exchange, "step": "health_check"},
            )
            return False

    async def close(self) -> None:
        await self.validator.close()
        await self.health_checker.close()
        await self.notifier.close()


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Rotate exchange API keys with validation and bluegreen deploy",
    )
    parser.add_argument(
        "--exchange",
        choices=["binance", "bitso"],
        required=True,
        help="Exchange to rotate keys for",
    )
    parser.add_argument(
        "--api-key",
        help="New API key (or set EXCHANGE_API_KEY env var)",
    )
    parser.add_argument(
        "--api-secret",
        help="New API secret (or set EXCHANGE_API_SECRET env var)",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Only validate keys, don't deploy",
    )
    parser.add_argument(
        "--skip-deploy",
        action="store_true",
        help="Update secrets but skip deployment",
    )
    parser.add_argument(
        "--app-name",
        default="stonks-trading-api",
        help="Fly.io app name (default: stonks-trading-api)",
    )

    args = parser.parse_args()

    # Get keys from args or environment
    if args.exchange == "binance":
        api_key = args.api_key or settings.binance_api_key
        api_secret = args.api_secret or settings.binance_api_secret
    else:  # bitso
        api_key = args.api_key or settings.bitso_api_key
        api_secret = args.api_secret or settings.bitso_api_secret

    if not api_key or not api_secret:
        logger.error(
            f"API credentials required. Provide via --api-key/--api-secret "
            f"or EXCHANGE_API_KEY/EXCHANGE_API_SECRET environment variables"
        )
        return 1

    async def run() -> int:
        orchestrator = KeyRotationOrchestrator()
        try:
            success = await orchestrator.rotate(
                exchange=args.exchange,
                api_key=api_key,
                api_secret=api_secret,
                validate_only=args.validate_only,
                skip_deploy=args.skip_deploy,
            )
            return 0 if success else 1
        finally:
            await orchestrator.close()

    return asyncio.run(run())


if __name__ == "__main__":
    sys.exit(main())
