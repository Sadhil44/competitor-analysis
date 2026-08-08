"""App settings (from env) and the competitors.yaml loader.

Two distinct kinds of config live here, deliberately kept separate:
- `Settings`: infrastructure config (DB URL, API keys) — from environment
  variables, via pydantic-settings.
- `CompetitorConfig`: the competitor/crawl-target list — from
  config/competitors.yaml, the single source of truth for what to crawl.
"""

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    anthropic_api_key: str = ""
    voyage_api_key: str = ""
    competitors_config_path: Path = Path("/config/competitors.yaml")
    own_brands_config_path: Path = Path("/config/own_brands.yaml")
    environment: str = "development"


@lru_cache
def get_settings() -> Settings:
    return Settings()


class CrawlConfig(BaseModel):
    cadence_cron: str
    rate_limit_seconds: float = 2.0
    catalog_urls: list[str]


class CompetitorConfig(BaseModel):
    slug: str
    name: str
    website_url: str
    active: bool = True
    notes: str = ""
    crawl: CrawlConfig


class CompetitorsFile(BaseModel):
    competitors: list[CompetitorConfig]


@lru_cache
def load_competitors_config(path: Path | None = None) -> list[CompetitorConfig]:
    """Read and validate config/competitors.yaml.

    Cached (like Settings) since this file only changes on redeploy in
    practice; callers that need a fresh read during local editing can call
    `load_competitors_config.cache_clear()` first.
    """
    resolved_path = path or get_settings().competitors_config_path
    raw = yaml.safe_load(resolved_path.read_text())
    parsed = CompetitorsFile.model_validate(raw)
    return [c for c in parsed.competitors if c.active]


class OwnBrandConfig(BaseModel):
    brand_num: int
    slug: str
    name: str
    website_url: str = ""
    notes: str = ""


class OwnBrandsFile(BaseModel):
    own_brands: list[OwnBrandConfig]


@lru_cache
def load_own_brands_config(path: Path | None = None) -> list[OwnBrandConfig]:
    """Read and validate config/own_brands.yaml — the brand_num -> identity
    mapping for the first-party pricing feed (app/scraping/feed_import.py).
    Mirrors load_competitors_config's caching behavior.
    """
    resolved_path = path or get_settings().own_brands_config_path
    raw = yaml.safe_load(resolved_path.read_text())
    parsed = OwnBrandsFile.model_validate(raw)
    return parsed.own_brands
