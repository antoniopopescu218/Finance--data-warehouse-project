from abc import ABC, abstractmethod
from datetime import datetime


class VendorAdapter(ABC):
    source_id: str
    name: str
    description: str
    api_endpoint: str

    @abstractmethod
    def fetch_timeseries(
        self, symbol: str, start: datetime, end: datetime
    ) -> list[dict]:
        """Return list of timeseries dicts normalized to the DWH shape."""

    @abstractmethod
    def fetch_asset_attributes(self, symbol: str) -> dict:
        """Return provider-specific attributes for the asset."""

    def source_record(self) -> dict:
        return {
            "source_id": self.source_id,
            "name": self.name,
            "description": self.description,
            "api_endpoint": self.api_endpoint,
        }
