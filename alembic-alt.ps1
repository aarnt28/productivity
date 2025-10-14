docker exec -it Productivity-Tracker sh -lc '
python - <<PY
import os
from sqlalchemy import create_engine, text
db = os.getenv("DATABASE_URL","sqlite:///./data.db")
engine = create_engine(db, future=True)
sql = """
CREATE TABLE IF NOT EXISTS sku_aliases (
  id INTEGER PRIMARY KEY,
  hardware_id INTEGER NOT NULL REFERENCES hardware(id) ON DELETE CASCADE,
  alias VARCHAR(128) NOT NULL,
  kind  VARCHAR(32) NOT NULL DEFAULT 'UPC',
  created_at DATETIME NOT NULL DEFAULT (CURRENT_TIMESTAMP)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_sku_aliases_alias ON sku_aliases(alias);
"""
with engine.begin() as conn:
    conn.exec_driver_sql(sql)
print("sku_aliases ready against", db)
PY
'
