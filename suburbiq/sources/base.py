"""The source-adapter seam.

This is the interface that de-risks the whole product: because fetching is
isolated here, a source becoming unavailable (as Yellow Pages has) costs us one
adapter rather than the system.
"""
from abc import ABC, abstractmethod
from typing import Iterator

from ..models import Area, RawRecord


class SourceAdapter(ABC):
    #: provenance tag written onto every row
    name: str = "base"
    #: rendered in the dashboard footer
    licence: str = ""

    @abstractmethod
    def fetch(self, category: str, area: Area) -> Iterator[RawRecord]:
        """Yield raw records for a category within an area.

        Raises:
            SourceBlocked: if the source refuses automated access.
        """
        raise NotImplementedError
