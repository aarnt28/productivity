# Productivity Billing Stack

This repo now contains a three-layer catalog ➝ inventory ➝ work/billing stack with a Shortcut-friendly API surface and a lightweight billing UI. Everything continues to run on the existing FastAPI app, bound to `127.0.0.1:8075` for the Zoraxy proxy path.

## Data Model Overview

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

* All monetary values are stored as `DECIMAL` with two or four fraction digits depending on intent.
* `StockLedger` is append-only; `ADJUST` rows represent corrections. FIFO depletion happens via `inventory_lots`.
* `TimeEntry`, `PartUsage`, `StockLedger`, and `Invoice` rows are stamped with `created_at`/`created_by` to preserve audit trails.

## API Surface

### Catalog (`/api/catalog`)
| Method | Path | Description |
| --- | --- | --- |
| GET | `/items?query=` | Search catalog items by name or SKU. |
| POST | `/items` | Create or update a catalog item (upsert by SKU). |
| POST | `/aliases` | Attach an additional alias (UPC/EAN/MPN/vendor SKU). |
| GET | `/resolve/{alias}` | Resolve an alias/SKU; first-time scans auto-create a minimal item and alias. |

### Inventory (`/api/inventory`)
| Method | Path | Description |
| --- | --- | --- |
| POST | `/receipt` | Receive stock into a warehouse (creates lots + ledger RECEIPT rows). |
| POST | `/adjust` | Admin adjustments (positive ➝ ADJUST receipt, negative ➝ ADJUST issues). |
| GET | `/stock?warehouse_id=` | On-hand snapshot per catalog item. |
| GET | `/ledger?from=&to=&warehouse_id=` | Movement history filtered by ISO timestamps. |

### Work (`/api/work`)
| Method | Path | Description |
| --- | --- | --- |
| POST | `/orders` | Open a work order for a client/project. |
| POST | `/time/start` | Start a timer (creates/open work order as needed). |
| POST | `/time/stop` | Stop the latest running timer or by explicit ID. |
| POST | `/parts/issue` | Issue parts by alias/SKU with FIFO costing; returns `part_usage` + ledger moves. |

### Billing (`/api/billing`)
| Method | Path | Description |
| --- | --- | --- |
| GET | `/unbilled?client_id=` | Aggregated unbilled time, parts, and flat tasks. |
| POST | `/invoices` | Build a draft invoice from selected sources. |
| POST | `/invoices/{id}/finalize` | Finalize a draft (status `sent` or `paid`). |

### Reports (`/api/reports`)
| Method | Path | Description |
| --- | --- | --- |
| GET | `/daily-rollup?date=YYYY-MM-DD` | Revenue (draft/invoiced/paid) vs issue-side COGS, normalized to America/Chicago. |

All new endpoints require `X-API-Key` unless an authenticated UI session is present.

## UI Additions

* **Billing workspace**: `/billing` renders a three-pane HTMX-free page for filters, unbilled items, and invoice assembly. The page calls the JSON APIs directly and supports inline overrides for quantity, bill/sell rates, discount, and tax. Draft invoices can be finalized from the same screen.

Existing legacy UI pages continue to function; `InventoryEvent` remains mapped for backwards compatibility with the old inventory screens.

## Database & Migrations

* New Alembic revision: `alembic/versions/20251014_02_three_layer_model.py`
  * Creates `catalog_items`, `sku_aliases` (new structure), `labor_roles`, `flat_tasks`, `warehouses`, `inventory_lots`, `stock_ledger`, `clients`, `projects`, `work_orders`, `time_entries`, `part_usage`, `invoices`, and `invoice_lines`.
  * Renames the legacy `sku_aliases` table to `sku_aliases_hardware` when present, preserving historic data.
  * Keeps the legacy `inventory_events` table untouched for the existing UI.
* Run migrations from the repo root:

```
poetry run alembic upgrade head   # or `alembic upgrade head` if using system tooling
```

## Smoke Tests

Set `TOKEN` to a valid API key (or leave unset when `API_TOKEN` is blank for dev), then:

```
curl -H "X-API-Key: $TOKEN" https://tracker.turnernet.co/api/catalog/resolve/012345678905

curl -X POST -H "X-API-Key: $TOKEN" -H "Content-Type: application/json" \
  -d '{"alias":"VND-ABC-789","kind":"VendorSKU","catalog_item_id":123}' \
  https://tracker.turnernet.co/api/catalog/aliases
```

Additional quick checks:

```
# confirm inventory ledger is reachable
curl -H "X-API-Key: $TOKEN" 'https://tracker.turnernet.co/api/inventory/ledger?from=2025-01-01&to=2025-01-31'

# create a draft invoice from the CLI (example payload)
curl -X POST -H "X-API-Key: $TOKEN" -H "Content-Type: application/json" \
  -d '{"client_id":1,"tax":0,"lines":[{"line_type":"labor","description":"Site visit","qty":1.0,"unit_price":125,"source_type":"time_entry","source_id":42}]}' \
  https://tracker.turnernet.co/api/billing/invoices
```

## Verification & Dev Notes

* Targeted syntax check of new modules:

```
python -m compileall \
  app/models/{catalog,billing,work,inventory}.py \
  app/routers/{catalog,inventory,work,billing,reports}.py \
  app/services/{barcode,stock,costing,billing}.py \
  app/schemas/{catalog,inventory,work,billing}.py
```

* The daily rollup operates in UTC internally but slices days in `America/Chicago` to match reporting expectations.
* Legacy `crud` and UI modules that still depend on `InventoryEvent` will continue to work; plan future cleanup once the new flows replace them fully.
