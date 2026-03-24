"""
Base source classes for paper and blog sources.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from paperfeeder.models import Paper


class BaseSource(ABC):
    """Abstract base class for all paper sources."""

    @abstractmethod
    async def fetch(self, **kwargs) -> List[Paper]:
        """Fetch papers from this source."""
        raise NotImplementedError

