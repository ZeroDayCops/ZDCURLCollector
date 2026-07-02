"""
Pydantic models for request/response validation
"""

from typing import Optional
from pydantic import BaseModel, HttpUrl, Field, field_validator


class ScrapeRequest(BaseModel):
    url: HttpUrl = Field(..., description="Social media profile URL to scrape")
    max_posts: int = Field(default=20, ge=1, le=50, description="Number of posts to fetch (1-50)")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "url": "https://www.instagram.com/abhivadan.store/",
                    "max_posts": 20
                }
            ]
        }
    }


class PostItem(BaseModel):
    post_url: str = Field(..., description="Direct URL to the post")
    caption: Optional[str] = Field(None, description="Post caption or title")
    thumbnail_url: Optional[str] = Field(None, description="Thumbnail/preview image URL")
    posted_at: Optional[str] = Field(None, description="Post date/time if available")
    likes: Optional[int] = Field(None, description="Like count if available")
    platform: str = Field(..., description="Source platform name")
    type: Optional[str] = Field(None, description="Content type: post or reel")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "post_url": "https://www.instagram.com/p/ABC123/",
                    "caption": "Check out our new collection! #fashion",
                    "thumbnail_url": "https://cdn.instagram.com/...",
                    "posted_at": "2024-01-15T10:30:00",
                    "likes": 1234,
                    "platform": "instagram"
                }
            ]
        }
    }


class ScrapeResponse(BaseModel):
    platform: str = Field(..., description="Detected platform name")
    profile_url: str = Field(..., description="Original profile URL")
    posts_found: int = Field(..., description="Number of posts retrieved")
    posts: list[PostItem] = Field(..., description="List of post items")
    scrape_status: str = Field(default="success", description="Status: success / partial / failed")
    message: Optional[str] = Field(None, description="Additional info or warnings")


class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None
