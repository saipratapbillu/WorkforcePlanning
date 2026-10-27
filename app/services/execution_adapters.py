from __future__ import annotations

import os
import json
import re
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlparse

import requests


class SecretResolutionError(Exception):
    pass


class SecretNotFound(SecretResolutionError):
    pass


class SecretResolverUnavailable(SecretResolutionError):
    pass


class SecretResolver(Protocol):
    def resolve(self, reference: str) -> str: ...


class LocalEnvironmentSecretResolver:
    """Development-only resolver for environment variables; never reads secret values from SQL."""

    def resolve(self, reference: str) -> str:
        match = re.fullmatch(r"env://([A-Z][A-Z0-9_]{0,127})", reference)
        if not match:
            raise SecretNotFound("Local secret references must use env://VARIABLE_NAME.")
        value = os.getenv(match.group(1))
        if not value:
            raise SecretNotFound("Referenced environment secret is not configured.")
        return value


class AzureKeyVaultSecretResolver:
    """Azure Key Vault resolver using DefaultAzureCredential and a preconfigured vault URL."""

    def __init__(self, vault_url: str | None = None):
        self.vault_url = (vault_url or os.getenv("AZURE_KEY_VAULT_URL", "")).rstrip("/")

    def resolve(self, reference: str) -> str:
        if not self.vault_url:
            raise SecretResolverUnavailable("AZURE_KEY_VAULT_URL is not configured.")
        match = re.fullmatch(r"azure-kv://([A-Za-z0-9-]{1,127})(?:/([A-Za-z0-9-]{1,127}))?", reference)
        if not match:
            raise SecretNotFound("Azure Key Vault reference must use azure-kv://secret-name[/version].")
        try:
            from azure.identity import DefaultAzureCredential
            from azure.keyvault.secrets import SecretClient
        except ImportError as exc:
            raise SecretResolverUnavailable("Azure Key Vault dependencies are not installed.") from exc
        try:
            client = SecretClient(vault_url=self.vault_url, credential=DefaultAzureCredential())
            secret = client.get_secret(match.group(1), match.group(2))
        except Exception as exc:
            raise SecretResolutionError("Azure Key Vault secret resolution failed.") from exc
        if not secret.value:
            raise SecretNotFound("Azure Key Vault returned an empty secret.")
        return secret.value


def configured_secret_resolver() -> SecretResolver:
    provider = os.getenv("AI_WORKFORCE_SECRET_PROVIDER", "").lower()
    if provider == "local":
        return LocalEnvironmentSecretResolver()
    if provider == "azure-key-vault":
        return AzureKeyVaultSecretResolver()
    raise SecretResolverUnavailable("Set AI_WORKFORCE_SECRET_PROVIDER to a configured vault provider.")


@dataclass(frozen=True)
class ProbeResult:
    status: str
    details: str
    http_status: int | None = None


_PROVIDER_HOSTS = {
    "AZURE_OPENAI": ("openai.azure.com",),
    "OPENAI": ("api.openai.com",),
    "GOOGLE_VERTEX": ("aiplatform.googleapis.com",),
    "ANTHROPIC": ("api.anthropic.com",),
}


def _validated_endpoint(provider_code: str, endpoint_url: str) -> str:
    parsed = urlparse(endpoint_url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Endpoint must be an HTTPS provider URL without embedded credentials.")
    if parsed.port not in (None, 443):
        raise ValueError("Provider endpoint must use standard HTTPS port 443.")
    host = parsed.hostname.lower().rstrip(".")
    if not any(host == suffix or host.endswith("." + suffix) for suffix in _PROVIDER_HOSTS[provider_code]):
        raise ValueError("Endpoint hostname is not allowed for the selected provider.")
    if parsed.query or parsed.fragment:
        raise ValueError("Endpoint must not include a query string or fragment.")
    return endpoint_url.rstrip("/")


def probe_provider(provider_code: str, endpoint_url: str, deployment_name: str, secret: str) -> ProbeResult:
    """Run an authenticated, bounded provider API request. Never returns response bodies or credentials."""
    try:
        endpoint = _validated_endpoint(provider_code, endpoint_url)
    except (KeyError, ValueError):
        return ProbeResult("ConfigurationIncomplete", "Provider endpoint configuration is invalid.")

    headers: dict[str, str]
    params: dict[str, str] | None = None
    if provider_code == "AZURE_OPENAI":
        headers = {"api-key": secret}
        params = {"api-version": os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21")}
        url = f"{endpoint}/openai/models"
    elif provider_code == "OPENAI":
        headers = {"Authorization": f"Bearer {secret}"}
        url = f"{endpoint}/v1/models"
    elif provider_code == "ANTHROPIC":
        headers = {"x-api-key": secret, "anthropic-version": "2023-06-01"}
        url = f"{endpoint}/v1/models"
    elif provider_code == "GOOGLE_VERTEX":
        try:
            from google.auth.transport.requests import Request
            from google.oauth2 import service_account
            credential_info = json.loads(secret)
            credentials = service_account.Credentials.from_service_account_info(
                credential_info,
                scopes=["https://www.googleapis.com/auth/cloud-platform"],
            )
            credentials.refresh(Request())
            access_token = credentials.token
        except ImportError:
            return ProbeResult("ConfigurationIncomplete", "Google authentication dependencies are not installed.")
        except (ValueError, TypeError, KeyError):
            return ProbeResult("ConfigurationIncomplete", "Vault credential is not a valid Google service-account credential document.")
        except Exception:
            return ProbeResult("Error", "Google application-default authentication failed.")
        headers = {"Authorization": f"Bearer {access_token}"}
        resource = deployment_name.strip("/")
        if not resource.startswith("projects/") or "/locations/" not in resource or "/publishers/" not in resource:
            return ProbeResult("ConfigurationIncomplete", "Vertex model resource must be a full projects/.../locations/.../publishers/.../models/... path.")
        url = f"{endpoint}/v1/{resource}"
    else:
        return ProbeResult("ConfigurationIncomplete", "Unsupported provider code.")

    try:
        response = requests.get(url, headers=headers, params=params, timeout=(3.05, 5), allow_redirects=False)
    except requests.Timeout:
        return ProbeResult("Unhealthy", "Provider request timed out.")
    except requests.RequestException:
        return ProbeResult("Error", "Provider request failed before receiving an HTTP response.")

    if 200 <= response.status_code < 300:
        return ProbeResult("Healthy", "Authenticated provider API request succeeded.", response.status_code)
    if response.status_code in (401, 403):
        return ProbeResult("Unhealthy", "Provider rejected authentication or authorization.", response.status_code)
    return ProbeResult("Unhealthy", "Provider API returned a non-success HTTP status.", response.status_code)
