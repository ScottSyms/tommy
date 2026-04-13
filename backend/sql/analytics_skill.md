## Purpose

Generate a single read-only SQL query for maritime analytics questions against approved backend-owned views.

## Allowed Views

- `cop_ship_positions`
- `cop_ship_identity`
- `cop_latest_ship_positions`

## Column Dictionary

### `cop_ship_positions`

- `position_id` text: unique position UUID
- `mmsi` bigint: vessel MMSI
- `timestamp` timestamp: event time in UTC offset-preserving ISO format
- `lat` double: latitude
- `lon` double: longitude
- `sog` double: speed over ground in knots
- `cog` double: course over ground in degrees
- `heading` double: vessel heading
- `nav_status` integer: AIS navigation status code
- `destination` text: raw destination text
- `destination_normalized` text: normalized destination string for fuzzy matching
- `name` text: vessel name
- `flag` text: vessel flag
- `ship_type` integer: AIS ship type

### `cop_ship_identity`

- `mmsi` bigint
- `imo` bigint
- `name` text
- `call_sign` text
- `ship_type` integer
- `flag` text
- `length` double
- `beam` double

### `cop_latest_ship_positions`

- latest single position per MMSI with the same positional columns as `cop_ship_positions`

## Domain Rules

- Prefer the selected ship MMSI when the user omits the ship subject.
- Use `destination_normalized` for fuzzy destination matching.
- Reads include overlay-composed state, not just immutable seed data.
- Destination history questions often need aggregates such as first seen, last seen, count, max, or min.
- Speed questions usually use `MAX(sog)`, `MIN(sog)`, or aggregates over `cop_ship_positions`.

## SQL Safety Rules

- Only output one statement.
- Only output `SELECT` or `WITH ... SELECT`.
- Never output prose outside a fenced SQL block.
- Never reference raw Parquet paths, temp files, or internal tables.
- Only use approved views listed above.
- If the query uses more than one relation in `FROM` or `JOIN`, give each relation an alias and qualify every selected, filtered, grouped, and ordered column with that alias.
- Never use bare column names like `mmsi`, `timestamp`, `lat`, `lon`, `name`, or `destination` after introducing a second relation.
- Always include a bounded result set with `LIMIT` unless the query is guaranteed to return one row through aggregation.

## Output Contract

Return only a fenced SQL block.

```sql
SELECT ...
```

## Worked Examples

### Has this ship been to Boston?

```sql
SELECT
  COUNT(*) > 0 AS visited_boston,
  MIN(timestamp) AS first_seen,
  MAX(timestamp) AS last_seen,
  COUNT(*) AS visit_count
FROM cop_ship_positions
WHERE mmsi = 316000000
  AND destination_normalized LIKE '%boston%';
```

### When was it there?

```sql
SELECT
  MIN(timestamp) AS first_seen,
  MAX(timestamp) AS last_seen
FROM cop_ship_positions
WHERE mmsi = 316000000
  AND destination_normalized LIKE '%boston%';
```

### What's the fastest it's travelled?

```sql
SELECT
  MAX(sog) AS max_sog,
  arg_max(timestamp, sog) AS max_sog_timestamp
FROM cop_ship_positions
WHERE mmsi = 316000000;
```

### How many times has it been to Halifax?

```sql
SELECT
  COUNT(*) AS matching_positions,
  MIN(timestamp) AS first_seen,
  MAX(timestamp) AS last_seen
FROM cop_ship_positions
WHERE mmsi = 316000000
  AND destination_normalized LIKE '%halifax%';
```

### Show the latest position with vessel identity

```sql
SELECT
  lp.mmsi,
  id.name,
  lp.timestamp,
  lp.lat,
  lp.lon,
  lp.destination
FROM cop_latest_ship_positions AS lp
JOIN cop_ship_identity AS id ON id.mmsi = lp.mmsi
WHERE lp.mmsi = 316000000
LIMIT 1;
```

## Follow-up Resolution Notes

- If the current question is a follow-up like `When?`, assume the backend has already resolved the omitted subject and destination from recent chat history.
- Do not ask clarifying questions in SQL output. Generate SQL for the resolved prompt you receive.
