# Productivity App — Developer Guide

This repository hosts a FastAPI application that tracks time, parts, and billing. The app currently exposes both a “new” three‑layer domain (Catalog → Inventory → Work/Billing/Reports) and a set of legacy endpoints used by the original UI. This guide documents the architecture, data model, APIs, dependencies, and how to develop and migrate the database.

Highlights

- FastAPI app served by Uvicorn on port 8090
- SQLite by default, SQLAlchemy 2.0 typed models, Alembic migrations
- API‑key auth for headless APIs; cookie session for UI
- New three‑layer APIs alongside legacy APIs retained for backward compatibility


## Quick Start

1) Run with Docker Compose

```
docker-compose up --build -d
```

- API base URL: http://localhost:8090
- UI login page: http://localhost:8090/login
- Data volume: `./data` on the host, mounted as `/data` in the container

2) Configure environment (compose defaults shown)

- `API_TOKEN`: required for `/api/*` unless using a logged‑in UI session
- `DB_URL`: e.g., `sqlite:////data/data.db`
- `TZ`: default `America/Chicago`
- `APP_SECRET`, `UI_USERNAME`, `UI_PASSWORD` or `UI_PASSWORD_HASH` (bcrypt)
- `SESSION_COOKIE_NAME`, `SESSION_MAX_AGE`


## Architecture Overview

- Application: `app/__init__.py` — creates the FastAPI app, registers routes, sessions, and runs migrations at startup
- Core
  - Config: `app/core/config.py` — centralizes env vars, paths, and runtime options
  - Jinja: `app/core/jinja.py` — shared template environment and filters
  - Barcodes: `app/core/barcodes.py` — normalization and alias generation for hardware barcodes (legacy layer)
- Database
  - Session/Engine/Base: `app/db/session.py`
  - Lightweight in‑app migrations for select legacy tables: `app/db/migrate.py`
  - Alembic migrations for the normalized (three‑layer) schema: `alembic/versions/*.py`
- Models (SQLAlchemy 2.0 typed)
  - Catalog: `app/models/catalog.py` — `CatalogItem`, `SkuAlias`, `LaborRole`, `FlatTask`
  - Inventory: `app/models/inventory.py` — `Warehouse`, `InventoryLot`, `StockLedger` (+ legacy `InventoryEvent`)
  - Work: `app/models/work.py` — `Client`, `Project`, `WorkOrder`, `TimeEntry`, `PartUsage`
  - Billing: `app/models/billing.py` — `Invoice`, `InvoiceLine`
  - Legacy: `app/models/hardware.py`, `app/models/ticket.py`
- Services
  - Barcode resolution for catalog: `app/services/barcode.py`
  - Stock receipt/issue (FIFO): `app/services/stock.py`
  - Billing assembly + unbilled discovery: `app/services/billing.py`
  - Reporting (legacy tickets): `app/services/reporting.py`
  - Client table sync and normalization: `app/services/clientsync.py`
- Routers
  - New API namespaces: `app/routers/catalog.py`, `app/routers/inventory.py`, `app/routers/work.py`, `app/routers/billing.py`, `app/routers/reports.py`
  - Legacy API namespaces: `app/routers/api_hardware.py`, `app/routers/api_inventory.py`, `app/routers/api_tickets.py`, `app/routers/api_reports.py`, `app/routers/api_catalog.py`
  - UI routes: `app/routers/ui.py`, `app/routers/auth_ui.py`


## Data Model (normalized)

```
Clients 1---* Projects 1---* WorkOrders 1---* TimeEntries
   |                             |             
   |                             *---* PartUsage *---* CatalogItems *---* InventoryLots *---* StockLedger
   |                                                     |                      
   |                                                     *---* SkuAliases      
   *---* Invoices *---* InvoiceLines (time_entry | part_usage | flat_task)

CatalogItems *---* LaborRoles (via TimeEntries)
CatalogItems *---* FlatTasks (templates for flat-rate labor)
Warehouses provide on-hand visibility through InventoryLots and StockLedger.
```

Conventions

- Currency: `Numeric(12, 2)` for monetary amounts; internal costing uses `Decimal`
- Quantities: `Numeric(14, 4)` for inventory deltas; FIFO depletion through `InventoryLot`
- Timestamps: stored in UTC; reporting normalizes to `America/Chicago` where applicable
- Integrity: `UniqueConstraint`, `CheckConstraint`, and named `Enum` types for clarity


## Authentication

- API key: All new APIs enforce `X-API-Key` unless a valid UI session exists; see `app/deps/auth.py`
- UI session: Cookie‑based session via Starlette; login flows in `app/routers/auth_ui.py`
- Compose provides a demo bcrypt hash; rotate `APP_SECRET` and `UI_PASSWORD_HASH` for production


## API Surface (new)

Base path: `/api/v2`

Catalog - `/api/v2/catalog`

- GET `/items?query=&limit=` → search by SKU or name
- POST `/items` → upsert by `sku`; `CatalogItemCreate`
- POST `/aliases` → attach alias (`UPC`/`EAN`/`MPN`/`VendorSKU`) to a `CatalogItem`
- GET `/resolve/{alias}` → resolve any alias/SKU; first‑scan can auto‑create placeholder

Inventory - `/api/v2/inventory`

- POST `/receipt` → receive to a `Warehouse` (creates `InventoryLot` + `StockLedger` receipt)
- POST `/adjust` → positive adjustments create stock; negatives issue via FIFO with cost capture
- GET `/stock?warehouse_id=` → on‑hand snapshot (per item) with total cost
- GET `/ledger?from=&to=&warehouse_id=` → movement history filtered by ISO timestamps

Work - `/api/v2/work`

- POST `/orders` → open a `WorkOrder`
- POST `/time/start` → start timer; creates/opens `WorkOrder` as needed
- POST `/time/stop` → stop latest or by explicit `time_entry_id`
- POST `/parts/issue` → issue parts by alias/SKU with FIFO costing; returns `PartUsage` + ledger moves

Billing - `/api/v2/billing`

- GET `/unbilled?client_id=` → unbilled time/parts/flat items
- POST `/invoices` → build draft invoice from selected sources
- POST `/invoices/{id}/finalize` → finalize as `sent` or `paid`

Reports - `/api/v2/reports`

- GET `/daily-rollup?date=YYYY-MM-DD` → revenue breakdown (draft/invoiced/paid) and COGS via `StockLedger`

All endpoints above require `X-API-Key` unless the caller holds a valid UI session.


## API Surface (legacy)

Base path: `/api/v1`

- Hardware: `app/routers/api_hardware.py`
- Inventory events: `app/routers/api_inventory.py`
- Tickets: `app/routers/api_tickets.py`
- Reports: `app/routers/api_reports.py`

Notes

- `api_catalog.py` is legacy/in-transition and currently mismatched with `app/services/barcode.py` and `app/schemas/catalog.py`. Prefer the new `/api/v2/catalog` router for the catalog domain.
- A reports router also exists for the new model at `app/routers/reports.py` under `/api/v2/reports`. Prefer this for greenfield work.


## Local Development

Run locally (without Docker)

```
python -m venv .venv
. .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install fastapi "uvicorn[standard]" sqlalchemy jinja2 python-multipart pydantic httpx itsdangerous bcrypt alembic pytest
export DB_URL=sqlite:///./data/dev.db
uvicorn app:app --host 0.0.0.0 --port 8090 --reload
```

Environment variables (core subset)

- `DB_URL` (default in Docker: `sqlite:////data/data.db`)
- `API_TOKEN` (empty allows all in dev)
- `APP_SECRET`, `UI_USERNAME`, `UI_PASSWORD` or `UI_PASSWORD_HASH`
- `TZ` (default: `America/Chicago`)


## Database & Migrations

Alembic is configured at the repo root. Use it for structural changes to the normalized model.

- Config: `alembic.ini`
- Env: `alembic/env.py`
- Revisions: `alembic/versions/*.py`

Common workflow

```
# point Alembic at your database
export DB_URL=sqlite:///./data/dev.db

# autogenerate a revision (ensure models are imported by alembic/env.py)
alembic revision --autogenerate -m "explain the change"

# apply
alembic upgrade head
```

Important revisions

- `20251014_01_add_sku_aliases.py` — legacy `sku_aliases` for hardware
- `20251014_02_three_layer_model.py` — normalized three‑layer schema; renames legacy `sku_aliases` → `sku_aliases_hardware` and creates catalog/inventory/work/billing tables

Startup migrations

- The app also runs a small set of idempotent, SQLite‑safe migrations at startup for historical tables (`app/db/migrate.py`). Prefer Alembic for all new schema changes.


## Testing

Tests live under `tests/`. To run:

```
pip install pytest
pytest -q
```

Representative coverage includes:

- Inventory costing and event lifecycle: `tests/test_inventory.py`
- Ticket metrics (legacy): `tests/test_reporting.py`, `tests/test_tickets.py`


## Coding Conventions

- SQLAlchemy 2.0 typed declarative models (`Mapped`, `mapped_column`) with explicit `Enum` types and `Numeric` for currency/quantities
- Pydantic v2 schemas (`model_dump`, `from_attributes = True`) under `app/schemas/*`
- Service layer encapsulates domain logic (costing, barcode resolution, billing); routers are thin
- Decimal math for money and quantities; round with `ROUND_HALF_UP`
- UTC timestamps in the DB; normalize to local TZ at the edges (templates, reporting)


## Security Notes

- Always set a strong `API_TOKEN` in production; clients must send `X-API-Key: <token>`
- Rotate `APP_SECRET`; prefer `UI_PASSWORD_HASH` (bcrypt) over `UI_PASSWORD`
- CORS is not configured by default; add it if exposing the API cross‑origin


## Known Gaps & TODOs

- `app/routers/api_catalog.py` references a missing `resolve_any_code` and returns a mismatched `ResolveResult` (hardware fields). It should be aligned with `app/services/barcode.resolve_catalog_item` and the new schemas, or deprecated in favor of `app/routers/catalog.py`.
- Duplicate reports endpoints exist (`api_reports.py` vs `reports.py`). Prefer `reports.py` built on the new model.
- The repository contains a checked‑in virtual environment folder (`productivity-app/`). Avoid committing venvs; consider adding it to `.gitignore`.
- `alembic-alt.ps1` is a legacy helper; prefer standard Alembic flows.


## Smoke Tests (new APIs)

```
TOKEN=your-api-token

# Catalog: resolve or create minimal item by scan
curl -H "X-API-Key: $TOKEN" http://localhost:8090/api/v2/catalog/resolve/012345678905

# Catalog: add alias
curl -X POST -H "X-API-Key: $TOKEN" -H "Content-Type: application/json" \
  -d '{"alias":"VND-ABC-789","kind":"VendorSKU","catalog_item_id":1}' \
  http://localhost:8090/api/v2/catalog/aliases

# Inventory: ledger window
curl -H "X-API-Key: $TOKEN" 'http://localhost:8090/api/v2/inventory/ledger?from=2025-01-01&to=2025-01-31'

# Reports: daily rollup (normalized model)
curl -H "X-API-Key: $TOKEN" 'http://localhost:8090/api/v2/reports/daily-rollup?date=2025-01-15'
```


## Operational Notes

- Container listens on `0.0.0.0:8090` (Dockerfile) and compose exposes `8090:8090`
- Data is persisted under `./data` by default; adjust `DB_URL`/`DATA_DIR` as needed
- UI pages are session‑gated; API key is not required when you have a logged‑in browser session


## Appendix: Directory Map (selected)

```
app/
  __init__.py                # FastAPI app wiring and startup
  core/                      # config, template env, barcode utils
  db/                        # SQLAlchemy engine, session, and small startup migrations
  models/                    # SQLAlchemy models (legacy + normalized)
  routers/                   # API and UI routes (legacy + new)
  schemas/                   # Pydantic v2 request/response models
  services/                  # domain services: stock, billing, barcode, reporting, clientsync
alembic/
  env.py                     # Alembic environment (imports models)
  versions/                  # migration history
docker-compose.yml           # container entrypoint and env defaults
Dockerfile                   # production image (Uvicorn @ 8090)
```

## Shortcuts-Friendly Endpoints

- Clients (legacy table): `/api/v1/clients` (app/routers/clients.py)
  - GET `/api/v1/clients` → `{ clients, attribute_keys }`
  - GET `/api/v1/clients/lookup?name=` → `{ client_key, client }`
  - GET `/api/v1/clients/{client_key}` → single `{ client_key, client }`
  - POST/PATCH/DELETE require UI session or `X-API-Key`

- Quick Issue (new): `/api/v2/work/items/quick-issue` (app/routers/work.py)
  - Minimal payload to issue a part to a client's active work order by barcode/SKU.
  - Accepts `client_id` or `client_key`/`client_name`, optional `project_id`, optional `warehouse_id` (uses only active warehouse if omitted), `alias`, and `qty`.

Example:

```
curl -X POST -H "X-API-Key: $TOKEN" -H "Content-Type: application/json" \
  -d '{
        "client_key": "client_a",
        "alias": "012345678905",
        "qty": 1
      }' \
  http://localhost:8090/api/v2/work/items/quick-issue
```

- Quick Time Start (new): `/api/v2/work/time/quick-start` (app/routers/work.py)
  - Start time for a client using `labor_role_name` (or `labor_role_id`), with `client_id` or `client_key`/`client_name`. Auto-creates/uses an active work order.

```
curl -X POST -H "X-API-Key: $TOKEN" -H "Content-Type: application/json" \
  -d '{
        "client_name": "Client A",
        "labor_role_name": "Support",
        "notes": "Remote session"
      }' \
  http://localhost:8090/api/v2/work/time/quick-start
```

- Quick Flat Invoice (new): `/api/v2/billing/quick-flat` (app/routers/billing.py)
  - Create a draft invoice with a single flat line for a client. Identify the item by `catalog_item_id` or `alias` (SKU/UPC/etc.). Provide `unit_price` if the item has no default price.

```
curl -X POST -H "X-API-Key: $TOKEN" -H "Content-Type: application/json" \
  -d '{
        "client_key": "client_a",
        "alias": "FLAT-CLEANUP",
        "qty": 1,
        "unit_price": 95
      }' \
  http://localhost:8090/api/v2/billing/quick-flat
```


## Shortcuts-Friendly Endpoints

- Clients (legacy table): `/api/v1/clients` (app/routers/clients.py)
  - GET `/api/v1/clients` → `{ clients, attribute_keys }`
  - GET `/api/v1/clients/lookup?name=` → `{ client_key, client }`
  - GET `/api/v1/clients/{client_key}` → single `{ client_key, client }`
  - POST/PATCH/DELETE require UI session or `X-API-Key`

- Quick Issue (new): `/api/v2/work/items/quick-issue` (app/routers/work.py)
  - Minimal payload to issue a part to a client's active work order by barcode/SKU.
  - Accepts `client_id` or `client_key`/`client_name`, optional `project_id`, optional `warehouse_id` (uses only active warehouse if omitted), `alias`, and `qty`.

Example:

```
curl -X POST -H "X-API-Key: $TOKEN" -H "Content-Type: application/json" \
  -d '{
        "client_key": "client_a",
        "alias": "012345678905",
        "qty": 1
      }' \
  http://localhost:8090/api/v2/work/items/quick-issue
```

