# Hotel MCP Server — Architecture & Design Reference

## Executive Summary

This server is an MCP-based integration layer that gives AI assistants and hotel
automation safe, structured access to operational data across Property Management
Systems (PMS) and Customer Relationship Management (CRM) platforms.

The central insight: hotel SaaS tools store overlapping guest data but cannot
communicate reliably. Staff copy records by hand; mismatches accumulate; guest
experiences suffer. This server provides a single, authoritative read layer with
a safe, human-approved write path — no direct database access, no tight coupling
to any one vendor.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     MCP Clients                                  │
│   Claude Desktop · Claude Code · Custom staff apps              │
└──────────────────────────────┬──────────────────────────────────┘
                               │  MCP protocol (stdio / SSE)
┌──────────────────────────────▼──────────────────────────────────┐
│                  Hotel MCP Server (FastMCP)                      │
│                                                                  │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────────────┐  │
│  │   Tools      │  │  Resources   │  │       Prompts          │  │
│  │─────────────│  │──────────────│  │────────────────────────│  │
│  │get_guest_pms│  │hotel://info  │  │check_in_preparation    │  │
│  │get_guest_crm│  │hotel://health│  │reconcile_guest_data    │  │
│  │compare_recs │  │hotel://schema│  │housekeeping_briefing   │  │
│  │get_reserv.  │  │hotel://policy│  │guest_complaint_triage  │  │
│  │get_room_st. │  └──────────────┘  │vip_arrival_alert       │  │
│  │unified_view │                    └────────────────────────┘  │
│  │suggest_sync │                                                  │
│  │find_dupes   │                                                  │
│  └──────┬──────┘                                                  │
│         │                                                         │
│  ┌──────▼────────────────────────────────┐                        │
│  │         Reconciliation Engine         │                        │
│  │  compare_records · build_sync_plan    │                        │
│  │  build_unified_view · mask_pii        │                        │
│  └──────┬────────────────────────────────┘                        │
│         │                                                         │
│  ┌──────▼────────────────────────────────┐                        │
│  │         Audit Logger (JSONL)          │                        │
│  │  every call → request_id + hash      │                        │
│  └──────┬────────────────────────────────┘                        │
└─────────┼───────────────────────────────────────────────────────┘
          │
┌─────────▼───────────────────────────────────────────────────────┐
│                    Adapter Layer                                  │
│                                                                  │
│  ┌─────────────────────┐    ┌─────────────────────┐             │
│  │    PMS Adapters      │    │    CRM Adapters      │             │
│  │─────────────────────│    │─────────────────────│             │
│  │OperaAdapter         │    │SalesforceAdapter     │             │
│  │CloudbedsAdapter [→] │    │HubSpotAdapter    [→] │             │
│  │MewsAdapter      [→] │    │ApaleoAdapter     [→] │             │
│  │MockPMSAdapter   [✓] │    │MockCRMAdapter    [✓] │             │
│  └──────────┬──────────┘    └────────┬────────────┘             │
└────────────┼──────────────────────────┼────────────────────────┘
             │                          │
    ┌────────▼──────┐        ┌──────────▼──────┐
    │ PMS REST API  │        │  CRM REST API    │
    │ (OPERA Cloud) │        │  (Salesforce)    │
    └───────────────┘        └─────────────────┘

[→] = on roadmap   [✓] = implemented
```

---

## Key Design Decisions

### 1. Adapter pattern — not direct API calls from tools
Tools call `BasePMSAdapter` / `BaseCRMAdapter` interfaces. Swapping from OPERA
to Mews requires only a new adapter class and a registry entry. No tool changes.

### 2. Read-only by default, write-by-exception
All seven core tools are `GET`-only. `suggest_sync_actions` returns a `SyncPlan`
with `write_enabled=False` always. A future `apply_sync_plan` tool will require
an explicit authorisation token in its call arguments and will be gated by role.

### 3. Audit-first
Every tool invocation writes a `pending` audit record before the tool runs and
a `success/error` record with duration after. This ensures failures are traceable
even when the upstream times out. Records are append-only JSONL; ship to SIEM.

### 4. PII masking in logs, hashing in audit records
Field values listed in `PII_FIELDS_MASK_IN_LOGS` are replaced with `<masked>`
in structured logs. Audit records store a SHA-256 hash of the full arguments,
not the raw values. Actual data lives only in the response to the MCP client.

### 5. European privacy baseline
- GDPR consent surfaced as a first-class field on `CRMGuest` and `UnifiedGuestView`.
- `hotel://policy/data-handling` resource gives AI assistants explicit rules
  about what to display and to whom.
- Data residency region is a config value, not hard-coded.
- Retention rules documented; anonymisation pipeline is a roadmap item.

### 6. Confidence scoring
`UnifiedGuestView.confidence_score` starts at 1.0 and decreases by 0.1 per
data-quality flag. Clients can use this to decide whether to surface a warning
before presenting guest data to staff.

---

## Folder Structure

```
hotel-mcp-server/
├── src/
│   ├── server.py               # FastMCP instance, wires everything
│   ├── config.py               # Pydantic-settings, env-var driven
│   ├── adapters/
│   │   ├── registry.py         # Adapter factory (maps env var → class)
│   │   ├── pms/
│   │   │   ├── base.py         # Abstract interface + exception types
│   │   │   ├── opera.py        # Oracle OPERA Cloud adapter
│   │   │   └── mock.py         # In-memory mock (dev + tests)
│   │   └── crm/
│   │       ├── base.py
│   │       ├── salesforce.py
│   │       └── mock.py
│   ├── models/
│   │   ├── guest.py            # PMSGuest, CRMGuest, UnifiedGuestView
│   │   ├── reservation.py
│   │   ├── room.py
│   │   ├── audit.py            # AuditContext
│   │   └── sync.py             # FieldDiff, SyncAction, SyncPlan
│   ├── tools/
│   │   ├── guest_tools.py      # get_guest_from_pms/crm, compare, unified
│   │   ├── reservation_tools.py
│   │   ├── room_tools.py
│   │   └── sync_tools.py       # suggest_sync_actions, find_duplicate_records
│   ├── resources/
│   │   └── hotel_resources.py  # hotel:// URI resources
│   ├── prompts/
│   │   └── hotel_prompts.py    # Staff-facing workflow prompts
│   └── utils/
│       ├── audit.py            # audit_tool_call context manager
│       └── reconcile.py        # compare_records, build_sync_plan, build_unified_view
├── tests/
│   └── test_reconcile.py
├── .env.example
├── .mcp.json                   # Claude Code integration
├── claude_desktop_config.example.json
└── pyproject.toml
```

---

## Security Notes

### Authentication
- `MCP_REQUIRE_AUTH=true` enables token checking in production.
- In v1, tokens are static bearer strings. Replace with OAuth 2.0 / OIDC
  (e.g. Okta, Azure AD) before any multi-tenant deployment.
- Adapter API keys are never logged. They live only in environment variables
  or a secrets manager (AWS Secrets Manager, HashiCorp Vault, GCP Secret Manager).

### What this server will NEVER do by default
- Execute writes without an explicit authorised write tool call.
- Store guest PII in logs.
- Return passport numbers or financial totals without role validation (roadmap).
- Cross-contaminate data between properties (property_id is always scoped).

---

## Roadmap

### Phase 2 — Write tools (Q3 2025)
- `apply_sync_action` — execute a single approved action from a SyncPlan.
  Requires `Authorization: Bearer <staff-token>` with `write:guest` scope.
- Role-based field masking: passport numbers only visible to `role=front_desk`.
- Webhook receiver: PMS pushes events → server invalidates cache, notifies clients.

### Phase 3 — Additional system connectors
| System | Adapter name | Priority |
|---|---|---|
| Mews PMS | `mews` | High |
| Apaleo PMS | `apaleo` | High |
| HubSpot CRM | `hubspot` | High |
| Oracle OPERA On-Prem | `opera_onprem` | Medium |
| Cloudbeds | `cloudbeds` | Medium |
| Duetto (Revenue) | `duetto` | Medium |
| SiteMinder (Channel Mgr) | `siteminder` | Medium |
| Oracle MICROS (POS) | `micros` | Low |
| Infor HMS | `infor` | Low |

### Phase 4 — Intelligence layer
- Nightly batch: compute duplicate-pair scores across entire guest database.
- Revenue contribution score per guest (PMS + POS combined).
- Predictive upgrade eligibility based on stay history + room availability.
- Multi-property guest profile federation for hotel groups.

### Phase 5 — Compliance & operations
- Anonymisation pipeline (GDPR Article 17 right to erasure).
- DSAR (Data Subject Access Request) tool — export all data for a guest.
- SOC 2 Type II audit log export.
- Multi-tenant isolation (each property group on isolated schema).
- SSE transport for web-based integrations (replaces stdio).
