"""Auth0 user model derived from JWT claims."""

from __future__ import annotations

from pydantic import BaseModel


class Auth0User(BaseModel):
    """Typed representation of an Auth0-authenticated user.

    Populated from decoded JWT claims via the ``from_claims`` factory.
    """

    sub: str
    email: str | None = None
    name: str | None = None
    picture: str | None = None
    email_verified: bool | None = None

    @classmethod
    def from_claims(cls, claims: dict) -> Auth0User:
        """Create an ``Auth0User`` from decoded JWT claims.

        Args:
            claims: Decoded JWT payload dictionary.

        Returns:
            An ``Auth0User`` instance with fields extracted from claims.
        """
        return cls(
            sub=claims["sub"],
            email=claims.get("email"),
            name=claims.get("name"),
            picture=claims.get("picture"),
            email_verified=claims.get("email_verified"),
        )
