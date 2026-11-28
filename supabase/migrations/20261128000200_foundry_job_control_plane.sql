-- Foundry durable job control-plane metadata.
-- No source/output bytes are stored here; object_key is an opaque external storage reference.
-- This migration changes only the Foundry-owned schema.

begin;

create table if not exists foundry.jobs (
    job_id uuid primary key default gen_random_uuid(),
    tenant_id text not null check (length(btrim(tenant_id)) between 1 and 255),
    actor_id text not null check (length(btrim(actor_id)) between 1 and 255),
    idempotency_key text not null check (length(idempotency_key) between 1 and 255),
    request_version text not null check (length(request_version) between 1 and 32),
    request_sha256 text not null check (request_sha256 ~ '^[0-9a-f]{64}$'),
    request_payload jsonb not null check (jsonb_typeof(request_payload) = 'object'),
    status text not null default 'queued'
        check (status in ('queued', 'running', 'succeeded', 'failed', 'cancelled', 'timed_out')),
    attempt_count integer not null default 0 check (attempt_count >= 0),
    max_attempts integer not null default 3 check (max_attempts between 1 and 20),
    available_at timestamptz not null default now(),
    lease_token uuid,
    lease_expires_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    started_at timestamptz,
    finished_at timestamptz,
    last_error jsonb,
    result_manifest jsonb,
    constraint jobs_tenant_id_job_id_key unique (tenant_id, job_id),
    constraint jobs_tenant_id_idempotency_key_key unique (tenant_id, idempotency_key),
    constraint jobs_lease_pair_check check (
        (lease_token is null and lease_expires_at is null)
        or (lease_token is not null and lease_expires_at is not null)
    ),
    constraint jobs_terminal_timestamp_check check (
        (status in ('succeeded', 'failed', 'cancelled', 'timed_out') and finished_at is not null)
        or (status in ('queued', 'running') and finished_at is null)
    ),
    constraint jobs_running_lease_check check (
        status <> 'running' or (lease_token is not null and lease_expires_at is not null)
    )
);

create index if not exists jobs_claim_queue_idx
    on foundry.jobs (available_at, created_at)
    where status = 'queued';
create index if not exists jobs_expired_lease_idx
    on foundry.jobs (lease_expires_at)
    where status = 'running';
create index if not exists jobs_tenant_created_idx
    on foundry.jobs (tenant_id, created_at desc);

create table if not exists foundry.job_events (
    event_id bigint generated always as identity primary key,
    tenant_id text not null check (length(btrim(tenant_id)) between 1 and 255),
    job_id uuid not null,
    event_type text not null check (length(btrim(event_type)) between 1 and 100),
    from_status text check (from_status in ('queued', 'running', 'succeeded', 'failed', 'cancelled', 'timed_out')),
    to_status text check (to_status in ('queued', 'running', 'succeeded', 'failed', 'cancelled', 'timed_out')),
    detail jsonb not null default '{}'::jsonb check (jsonb_typeof(detail) = 'object'),
    occurred_at timestamptz not null default now(),
    constraint job_events_tenant_job_fk
        foreign key (tenant_id, job_id)
        references foundry.jobs (tenant_id, job_id)
        on delete cascade
);
create index if not exists job_events_tenant_job_time_idx
    on foundry.job_events (tenant_id, job_id, occurred_at, event_id);

create table if not exists foundry.artifacts (
    artifact_id uuid primary key default gen_random_uuid(),
    tenant_id text not null check (length(btrim(tenant_id)) between 1 and 255),
    job_id uuid not null,
    artifact_kind text not null
        check (artifact_kind in ('source', 'intermediate', 'output', 'delivery', 'manifest')),
    logical_name text not null check (length(btrim(logical_name)) between 1 and 255),
    object_key text not null check (length(btrim(object_key)) between 1 and 2048),
    media_type text not null check (length(btrim(media_type)) between 1 and 255),
    format text,
    checksum_sha256 text not null check (checksum_sha256 ~ '^[0-9a-f]{64}$'),
    size_bytes bigint not null check (size_bytes >= 0),
    metadata jsonb not null default '{}'::jsonb check (jsonb_typeof(metadata) = 'object'),
    created_at timestamptz not null default now(),
    expires_at timestamptz,
    constraint artifacts_tenant_job_fk
        foreign key (tenant_id, job_id)
        references foundry.jobs (tenant_id, job_id)
        on delete cascade,
    constraint artifacts_tenant_object_key_key unique (tenant_id, object_key)
);
create index if not exists artifacts_tenant_job_created_idx
    on foundry.artifacts (tenant_id, job_id, created_at);
create index if not exists artifacts_expiry_idx
    on foundry.artifacts (expires_at)
    where expires_at is not null;

-- Tables are private by default. The server role is the only application role
-- granted access; it bypasses RLS, so tenant checks remain mandatory in trusted code.
revoke all on foundry.jobs, foundry.job_events, foundry.artifacts
    from public, anon, authenticated, service_role;
grant select, insert, update on foundry.jobs to service_role;
grant select, insert on foundry.job_events, foundry.artifacts to service_role;
grant usage, select on all sequences in schema foundry to service_role;

alter table foundry.jobs enable row level security;
alter table foundry.jobs force row level security;
alter table foundry.job_events enable row level security;
alter table foundry.job_events force row level security;
alter table foundry.artifacts enable row level security;
alter table foundry.artifacts force row level security;

comment on table foundry.jobs is
    'Durable asynchronous job control plane. Request payload contains bounded metadata only; source bytes live in external object storage.';
comment on table foundry.job_events is
    'Append-only job lifecycle/audit events; never store credentials or raw customer source data in event detail.';
comment on table foundry.artifacts is
    'Tenant-scoped artifact metadata and opaque object-storage keys; artifact bytes are not stored in Postgres.';

commit;
