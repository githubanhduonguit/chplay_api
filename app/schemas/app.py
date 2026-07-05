"""Schemas for app detail responses."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class RatingSchema(BaseModel):
    """Rating information for an app."""

    average: float = Field(..., description="Average rating (0-5)")
    count: int = Field(..., description="Total number of ratings")

    model_config = ConfigDict(from_attributes=True)


class DeveloperSchema(BaseModel):
    """Developer/company information."""

    name: Optional[str] = Field(None, description="Developer or company name")

    model_config = ConfigDict(from_attributes=True)


class AppDetailSchema(BaseModel):
    """Detailed app information response."""

    id: int = Field(..., description="App ID")
    packageName: str = Field(..., description="Unique package name")
    name: str = Field(..., description="App display name")
    icon: Optional[str] = Field(None, description="URL to app icon")
    rating: RatingSchema = Field(..., description="Rating information")
    createdAt: datetime = Field(..., description="When app was listed")

    model_config = ConfigDict(from_attributes=True)
