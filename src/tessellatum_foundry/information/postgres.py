"""PostgreSQL/PostGIS repository for Foundry's spatial information core.

The adapter accepts an already-open psycopg connection. Connection ownership,
pooling, authentication, and transaction boundaries remain with the application.
Importing this module does not require psycopg; install the optional postgis extra.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator


class PostgresInformationStore:
    """Small parameterized repository over the foundry PostGIS schema.

    Methods return dictionaries keyed by database column name. They do not
    commit implicitly: callers may group multiple writes in transaction()
    or manage transactions directly on their psycopg connection.
    """

    def __init__(self, connection: Any) -> None:
        self.connection = connection

    @contextmanager
    def transaction(self) -> Iterator[PostgresInformationStore]:
        """Group information writes in one psycopg transaction."""
        with self.connection.transaction():
            yield self

    @staticmethod
    def _json(value: dict[str, Any]) -> Any:
        try:
            from psycopg.types.json import Jsonb
        except ImportError as error:
            raise RuntimeError(
                "PostgresInformationStore requires the optional 'postgis' extra: "
                "pip install 'tessellatum-foundry[postgis]'."
            ) from error
        return Jsonb(value)

    def _one(self, query: str, params: tuple[Any, ...]) -> dict[str, Any]:
        with self.connection.cursor() as cursor:
            cursor.execute(query, params)
            row = cursor.fetchone()
            if row is None:
                raise RuntimeError("Database write did not return its inserted row.")
            return dict(zip((column.name for column in cursor.description), row, strict=True))

    def create_entity(
        self, *, entity_type: str, created_by: str,
        metadata: dict[str, Any] | None = None, lifecycle_state: str = "active",
    ) -> dict[str, Any]:
        """Create a stable geographic or modeled entity identity."""
        return self._one(
            """INSERT INTO foundry.entity
                   (entity_type, created_by, lifecycle_state, metadata)
               VALUES (%s, %s, %s, %s) RETURNING *""",
            (entity_type, created_by, lifecycle_state, self._json(metadata or {})),
        )

    def get_entity(self, entity_id: str) -> dict[str, Any]:
        """Fetch one entity by its exact Foundry UUID."""
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT * FROM foundry.entity WHERE entity_id = %s", (entity_id,))
            row = cursor.fetchone()
            if row is None:
                raise KeyError(f"Foundry entity {entity_id!r} was not found.")
            return dict(zip((column.name for column in cursor.description), row, strict=True))

    def register_source_dataset(
        self, *, source_key: str, title: str, registered_by: str,
        provider: str | None = None, description: str | None = None,
        declared_license: str | None = None, source_uri: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Register a stable provider/dataset identity; source_key is unique."""
        return self._one(
            """INSERT INTO foundry.source_dataset
                   (source_key, title, provider, description, declared_license,
                    source_uri, metadata, registered_by)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING *""",
            (source_key, title, provider, description, declared_license,
             source_uri, self._json(metadata or {}), registered_by),
        )

    def create_source_snapshot(
        self, *, source_dataset_id: str, snapshot_key: str,
        checksum_hex: str | None = None, captured_at: Any | None = None,
        source_uri: str | None = None, media_type: str | None = None,
        byte_size: int | None = None, metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Record one captured state of a source dataset."""
        return self._one(
            """INSERT INTO foundry.source_snapshot
                   (source_dataset_id, snapshot_key, captured_at, source_uri,
                    checksum_hex, media_type, byte_size, metadata)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING *""",
            (source_dataset_id, snapshot_key, captured_at, source_uri,
             checksum_hex, media_type, byte_size, self._json(metadata or {})),
        )

    def insert_source_record(
        self, *, source_snapshot_id: str, source_record_key: str,
        payload: dict[str, Any], source_layer: str | None = None,
        source_ordinal: int | None = None, payload_checksum: str | None = None,
    ) -> dict[str, Any]:
        """Preserve a provider row/feature as received, without assigning identity."""
        return self._one(
            """INSERT INTO foundry.source_record
                   (source_snapshot_id, source_record_key, source_layer,
                    source_ordinal, payload, payload_checksum)
               VALUES (%s, %s, %s, %s, %s, %s) RETURNING *""",
            (source_snapshot_id, source_record_key, source_layer,
             source_ordinal, self._json(payload), payload_checksum),
        )

    def link_source_record(
        self, *, entity_id: str, source_record_id: str, match_method: str,
        link_state: str = "proposed", confidence: float | None = None,
        rationale: str | None = None, decided_by: str | None = None,
    ) -> dict[str, Any]:
        """Create a source-to-entity crosswalk, optionally recording a decision."""
        if link_state == "proposed":
            if decided_by is not None:
                raise ValueError("decided_by must be omitted for a proposed link.")
            query = """INSERT INTO foundry.entity_source_link
                (entity_id, source_record_id, link_state, match_method, confidence, rationale)
                VALUES (%s, %s, %s, %s, %s, %s) RETURNING *"""
            params = (entity_id, source_record_id, link_state, match_method, confidence, rationale)
        else:
            if not decided_by:
                raise ValueError("decided_by is required for a non-proposed link.")
            query = """INSERT INTO foundry.entity_source_link
                (entity_id, source_record_id, link_state, match_method, confidence,
                 rationale, decided_at, decided_by)
                VALUES (%s, %s, %s, %s, %s, %s, now(), %s) RETURNING *"""
            params = (entity_id, source_record_id, link_state, match_method,
                      confidence, rationale, decided_by)
        return self._one(query, params)

    def add_observation(
        self, *, entity_id: str, observation_kind: str, recorded_by: str,
        assertion: dict[str, Any], source_record_id: str | None = None,
        observed_at: Any | None = None, valid_time: tuple[Any, Any] | None = None,
        confidence: float | None = None, supersedes_observation_id: str | None = None,
        provenance: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Append a source-backed or human-authored assertion about an entity."""
        lower, upper = valid_time if valid_time is not None else (None, None)
        return self._one(
            """INSERT INTO foundry.observation
                (entity_id, source_record_id, observation_kind, observed_at, valid_time,
                 recorded_by, assertion, confidence, supersedes_observation_id, provenance)
               VALUES (%s, %s, %s, %s,
                 CASE WHEN %s::timestamptz IS NULL AND %s::timestamptz IS NULL THEN NULL
                      ELSE tstzrange(%s::timestamptz, %s::timestamptz, '[)') END,
                 %s, %s, %s, %s, %s) RETURNING *""",
            (entity_id, source_record_id, observation_kind, observed_at,
             lower, upper, lower, upper, recorded_by, self._json(assertion),
             confidence, supersedes_observation_id, self._json(provenance or {})),
        )

    def add_representation(
        self, *, entity_id: str, representation_version: int,
        geometry_wkb: bytes, srid: int, recorded_by: str,
        observation_id: str | None = None, attributes: dict[str, Any] | None = None,
        valid_time: tuple[Any, Any] | None = None,
        supersedes_representation_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Append a geometry/attribute depiction; geometry never defines identity."""
        if not isinstance(geometry_wkb, bytes) or not geometry_wkb:
            raise TypeError("geometry_wkb must be non-empty WKB bytes.")
        if isinstance(srid, bool) or not isinstance(srid, int) or srid <= 0:
            raise ValueError("srid must be a positive integer.")
        lower, upper = valid_time if valid_time is not None else (None, None)
        return self._one(
            """INSERT INTO foundry.entity_representation
                (entity_id, representation_version, observation_id, geometry,
                 attributes, valid_time, recorded_by, supersedes_representation_id, metadata)
               VALUES (%s, %s, %s, ST_SetSRID(ST_GeomFromWKB(%s), %s), %s,
                 CASE WHEN %s::timestamptz IS NULL AND %s::timestamptz IS NULL THEN NULL
                      ELSE tstzrange(%s::timestamptz, %s::timestamptz, '[)') END, %s, %s, %s)
               RETURNING representation_id, entity_id, representation_version,
                 observation_id, ST_SRID(geometry) AS srid, ST_AsBinary(geometry) AS geometry_wkb,
                 attributes, valid_time, recorded_at, recorded_by,
                 supersedes_representation_id, metadata""",
            (entity_id, representation_version, observation_id, geometry_wkb, srid,
             self._json(attributes or {}), lower, upper, lower, upper,
             recorded_by, supersedes_representation_id, self._json(metadata or {})),
        )

    def add_relationship(
        self, *, subject_entity_id: str, relationship_type: str,
        object_entity_id: str, recorded_by: str,
        observation_id: str | None = None,
        valid_time: tuple[Any, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Append a directed, typed, time-qualified entity relationship."""
        lower, upper = valid_time if valid_time is not None else (None, None)
        return self._one(
            """INSERT INTO foundry.entity_relationship
                (subject_entity_id, relationship_type, object_entity_id,
                 observation_id, valid_time, recorded_by, metadata)
               VALUES (%s, %s, %s, %s,
                 CASE WHEN %s::timestamptz IS NULL AND %s::timestamptz IS NULL THEN NULL
                      ELSE tstzrange(%s::timestamptz, %s::timestamptz, '[)') END, %s, %s) RETURNING *""",
            (subject_entity_id, relationship_type, object_entity_id, observation_id,
             lower, upper, lower, upper, recorded_by, self._json(metadata or {})),
        )
