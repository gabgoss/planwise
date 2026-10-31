# FXP-META-S01-01-01 Ledger Survey

**Task:** FXP-META-S01-01-01
**Tier:** 1 (raw task output)
**Date:** 2026-10-31

---

## 1. Jar Record Fields

Every jar on a shelf is one record. The survey found six fields.

| # | Field | Type | Required | Notes |
|---|-------|------|----------|-------|
| 1 | `jar_id` | string | yes | Format `J-{shelf}{slot}`, for example `J-B07` |
| 2 | `label` | string | yes | Free text, at most 40 characters |
| 3 | `shelf` | letter | yes | `A` to `F` |
| 4 | `slot` | integer | yes | `1` to `12` |
| 5 | `fill_pct` | integer | yes | `0` to `100`, in steps of 5 |
| 6 | `sealed_on` | date | no | ISO date. Empty means unknown |

Six shelves times twelve slots gives 72 slots. The survey counted 41 jars in the sample pantry.

---

## 2. Ledger File Format

The ledger is one UTF-8 text file, `pantry.ledger`. Each line holds one record as `key=value` pairs separated by a single tab. A line that starts with `#` is a comment. Blank lines are ignored.

```
jar_id=J-B07	label=Plum jam	shelf=B	slot=7	fill_pct=60	sealed_on=2026-08-14
```

---

## 3. Operations the Ledger Needs

1. **Load** the file into memory and reject a duplicate `jar_id` with the line number.
2. **Add** a jar to an empty slot. Adding to an occupied slot is an error.
3. **Move** a jar to another empty slot. The `jar_id` changes to match the new slot.
4. **Refill** a jar, which sets `fill_pct` and clears nothing else.
5. **Save** the ledger back, sorted by shelf and then slot.

---

## 4. Open Observations

- Two sample jars had `fill_pct=33`, which is not a step of 5. The survey rounds such values down to the nearest step on load and logs a warning.
- The sample ledger had no comment lines. The format still allows them.
