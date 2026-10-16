# Data model

## Glucose readings: why `factory_timestamp` is the key

### The upsert needs a unique key

The `fetch_glucose` DAG runs hourly, and each run fetches the last ~12 hours of
readings, so ~11 of those hours are already stored. The load step therefore
**upserts**: for each reading it asks "do I already have this one?" and skips it
(or updates it) if so, instead of inserting a duplicate.

To answer that question the table needs a column whose value is **unique per
reading**: the key. Its one required property: two different readings must
never share the same value.

### Each reading has two timestamps

LibreLinkUp returns two timestamps for the same moment (fields of
`pylibrelinkup`'s `GlucoseMeasurement`):

| Field | Meaning | Example |
|---|---|---|
| `factory_timestamp` | Sensor time, in **UTC** | `2026-10-16 08:30` |
| `timestamp` | The phone's **local** time, no time zone | `2026-10-16 10:30` (Spain, UTC+2) |

They are the same moment in two "languages". The difference between them is
the local UTC offset.

### Local time can repeat

At the EU clock change in October (e.g. 25 October 2026), at 03:00 local time
clocks go **back** to 02:00, so the hour 02:00–03:00 happens **twice**. With a
reading every 15 minutes:

| What really happened | Local time (`timestamp`) | UTC (`factory_timestamp`) |
|---|---|---|
| 1st time through 02:30 | **02:30** | 00:30 |
| 2nd time through 02:30 (an hour later) | **02:30** | 01:30 |

Two **different** readings, an hour apart, have the **same local time**. Keyed on
`timestamp`, the upsert would see the second 02:30 reading, think "already have
it" and **discard it**: an hour of data silently lost every October.

In March the opposite happens: local time jumps from 02:00 to 03:00. Nothing
repeats, but there's a one-hour gap, which also makes local time awkward for
calculations.

UTC has no daylight saving time: it always moves forward, never repeats and
never skips. So `factory_timestamp` is unique per reading.

### Decision

- **`factory_timestamp` (UTC) is the table's primary key and the upsert key**
  (`INSERT ... ON CONFLICT (factory_timestamp) ...`).
- `timestamp` (local) is stored as a normal column, useful for questions about
  daily routine ("what is my glucose like at breakfast?").

To check it on real data: for any reading, `factory_timestamp` and `timestamp`
differ by exactly the local UTC offset (in Spain: 2 hours in summer time,
1 hour in winter time).

## No backfill of historical data

The table only holds readings from the moment the pipeline started running
(October 2026) onwards; older history is deliberately not loaded. The project
only cares about data from now on, and the LibreLinkUp API couldn't provide it
anyway: it doesn't return data older than 14 days, so a full history isn't
available from this source. That's also why the DAG uses `catchup=False`:
past runs would fetch the same recent window as a new run, not older data.