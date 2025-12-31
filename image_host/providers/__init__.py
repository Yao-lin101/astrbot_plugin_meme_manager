"""图床提供者模块"""

from .cloudflare_r2_provider import CloudflareR2Provider
from .provider_template import ProviderTemplate as ImageHostProvider
from .stardots_provider import StarDotsProvider

__all__ = ["StarDotsProvider", "CloudflareR2Provider", "ImageHostProvider"]
