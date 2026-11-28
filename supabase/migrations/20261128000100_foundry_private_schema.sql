-- Foundry's isolated metadata schema in the existing Panda Roam Supabase project.
-- This migration intentionally creates no tables and does not alter public/Panda Roam objects.
-- Keep "foundry" out of Supabase API exposed schemas; server-side access only.

begin;

create schema if not exists foundry authorization postgres;

revoke all on schema foundry from public;
revoke all on schema foundry from anon;
revoke all on schema foundry from authenticated;
grant usage on schema foundry to service_role;

-- No client role can create objects or resolve objects in this schema.
-- The service role receives schema usage only; object grants are explicit defaults.
alter default privileges for role postgres in schema foundry
  revoke all on tables from public, anon, authenticated, service_role;
alter default privileges for role postgres in schema foundry
  grant select, insert, update, delete on tables to service_role;

alter default privileges for role postgres in schema foundry
  revoke all on sequences from public, anon, authenticated, service_role;
alter default privileges for role postgres in schema foundry
  grant usage, select on sequences to service_role;

comment on schema foundry is
  'Foundry-owned private metadata schema. Keep outside Supabase API exposed schemas; server-side access only.';

commit;
