# Legacy Notes

## Pointer Fields

The `applied-as:` field names the artifact a lesson was promoted into.

## Superseded Fields

The `rule-as:` field is DEPRECATED — read it when an older record carries it, never
write it.

## Migration

When touching a record that still carries the DEPRECATED key, remap its value and
drop the key. That is a value remap, not a key rename.

## Current Scheme

`applied-as:` holds the artifact; `promoted-to:` holds the owner in id form.
