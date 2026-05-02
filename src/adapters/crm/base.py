"""Abstract CRM adapter — same pattern as BasePMSAdapter."""

from __future__ import annotations

from abc import ABC, abstractmethod

from src.models.guest import CRMGuest


class BaseCRMAdapter(ABC):

    @abstractmethod
    async def health_check(self) -> dict[str, str]: ...

    @abstractmethod
    async def get_contact_by_id(self, contact_id: str) -> CRMGuest: ...

    @abstractmethod
    async def get_contact_by_email(self, email: str) -> CRMGuest: ...

    @abstractmethod
    async def search_contacts(
        self,
        query: str,
        limit: int = 20,
    ) -> list[CRMGuest]: ...

    @abstractmethod
    async def get_contact_by_loyalty_number(self, loyalty_number: str) -> CRMGuest: ...
