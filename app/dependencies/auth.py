"""
JWT Validation Dependency.

Validates Auth0 JWT tokens using JWKS public keys.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from cachetools import TTLCache
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from app.core.config import settings
from app.schemas.auth import Auth0User

logger = logging.getLogger(__name__)

# Security scheme for OpenAPI docs
security = HTTPBearer()

# JWKS cache: cache JWKS keys for 10 minutes
_jwks_cache: TTLCache[str, dict] = TTLCache(maxsize=1, ttl=600)


async def _get_jwks() -> dict[str, Any]:
    """
    Fetch JWKS keys from Auth0, with caching.
    
    Returns:
        JWKS keys dictionary.
        
    Raises:
        HTTPException: If unable to fetch JWKS.
    """
    cache_key = "jwks"
    
    # Check cache first
    if cache_key in _jwks_cache:
        return _jwks_cache[cache_key]
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                settings.AUTH0_JWKS_URL,
                timeout=settings.TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            jwks = response.json()
            _jwks_cache[cache_key] = jwks
            return jwks
    except httpx.HTTPError as e:
        logger.error(f"Failed to fetch JWKS from Auth0: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to fetch authentication keys",
        )


def _get_signing_key(jwks: dict[str, Any], token: str) -> str:
    """
    Extract the signing key from JWKS for the given token.
    
    Args:
        jwks: JWKS keys dictionary.
        token: JWT token.
        
    Returns:
        The public key for verification.
        
    Raises:
        HTTPException: If unable to find matching key.
    """
    try:
        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get("kid")
        
        if not kid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: missing kid header",
            )
        
        # Find matching key
        for key in jwks.get("keys", []):
            if key["kid"] == kid:
                return key
        
        # If no matching key, it might be rotated - clear cache and try again
        _jwks_cache.pop("jwks", None)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token: no matching key found",
        )
    except JWTError as e:
        logger.error(f"Failed to decode token header: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {str(e)}",
        )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> Auth0User:
    """
    Validate JWT token and return a typed Auth0User.

    This dependency:
    1. Extracts Bearer token from Authorization header
    2. Fetches JWKS public key from Auth0 (with caching)
    3. Validates JWT signature, expiration, audience, and issuer
    4. Returns an Auth0User instance (sub, email, name, etc.)
    
    Args:
        credentials: HTTP Bearer credentials from request header.
        
    Returns:
        Auth0User instance built from the decoded JWT claims.
        
    Raises:
        HTTPException: 401 if token is invalid, expired, or missing.
    """
    token = credentials.credentials
    
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token",
        )
    
    try:
        # Get JWKS keys (with caching)
        jwks = await _get_jwks()
        
        # Get signing key for this token
        signing_key = _get_signing_key(jwks, token)
        
        # Decode and validate JWT
        payload = jwt.decode(
            token,
            signing_key,
            algorithms=settings.AUTH0_ALGORITHMS,
            audience=settings.AUTH0_AUDIENCE,
            issuer=settings.AUTH0_ISSUER,
        )
        
        return Auth0User.from_claims(payload)
        
    except JWTError as e:
        logger.warning(f"JWT validation failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {str(e)}",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error during JWT validation: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal authentication error",
        )
