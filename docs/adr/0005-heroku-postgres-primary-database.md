# 0005 — Heroku Postgres is the app's database; Supabase is a backup
Status: accepted
Source: task log 2026-06-24 (cutover after repeated Supabase free-tier auto-pauses); backup task 2026-10-09.

**Decision.** The app reads and writes Heroku Postgres. Supabase holds a one-off backup (schema
`backup_2026_10_09`) and the old May–June snapshot.
**Consequence.** "The data is in Supabase" (as said in the 2026-10-09 meeting and email) is only true of the
backup copy; any Softr migration should read from Heroku Postgres or a fresh export.
