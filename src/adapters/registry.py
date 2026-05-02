"""
Adapter registry — maps config strings to concrete adapter classes.
Add new adapters here; the tools layer never needs to change.
"""

from __future__ import annotations

from src.adapters.crm.base import BaseCRMAdapter
from src.adapters.pms.base import BasePMSAdapter
from src.config import settings


def get_pms_adapter() -> BasePMSAdapter:
    adapter_name = settings.pms.adapter.lower()

    if adapter_name == "opera":
        from src.adapters.pms.opera import OperaAdapter
        return OperaAdapter(settings.pms)

    if adapter_name == "cloudbeds":
        raise NotImplementedError("Cloudbeds adapter is on the roadmap — use mock for now")

    if adapter_name == "mews":
        from src.adapters.pms.mews import MewsAdapter
        return MewsAdapter(settings.pms)

    if adapter_name == "mock":
        from src.adapters.pms.mock import MockPMSAdapter
        return MockPMSAdapter()

    raise ValueError(f"Unknown PMS adapter: {adapter_name!r}. Valid: opera, mock")


def get_crm_adapter() -> BaseCRMAdapter:
    adapter_name = settings.crm.adapter.lower()

    if adapter_name == "salesforce":
        from src.adapters.crm.salesforce import SalesforceAdapter
        return SalesforceAdapter(settings.crm)

    if adapter_name == "hubspot":
        raise NotImplementedError("HubSpot adapter is on the roadmap — use mock for now")

    if adapter_name == "mock":
        from src.adapters.crm.mock import MockCRMAdapter
        return MockCRMAdapter()

    raise ValueError(f"Unknown CRM adapter: {adapter_name!r}. Valid: salesforce, mock")
