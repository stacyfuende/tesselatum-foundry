-- Correct the already-provisioned Foundry schema's default privileges.
-- Future objects receive no automatic application-role grants; grant explicitly per migration.

begin;
alter default privileges for role postgres in schema foundry
  revoke all on tables from public, anon, authenticated, service_role;
alter default privileges for role postgres in schema foundry
  revoke all on sequences from public, anon, authenticated, service_role;

-- The job_events identity column requires sequence usage for service_role inserts.
grant usage, select on sequence foundry.job_events_event_id_seq to service_role;
commit;
