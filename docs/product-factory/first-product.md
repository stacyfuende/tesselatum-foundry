# First Product Factory Example

This example is an outcome-first Product Blueprint. It declares a road-access product without embedding execution code.

## Flow

1. Validate the Blueprint against `spatial_product_blueprint.schema.json`.
2. Plan it against the registered Capability registry.
3. Resolve the `roads` evidence requirement to an immutable Artifact reference.
4. Supply a Cell template for `vector.buffer@1.0.0` with explicit spatial output contract.
5. Compile the plan into immutable Cells and a Recipe.
6. Execute through the existing Recipe Execution Service.
7. Evaluate acceptance checks.
8. Assemble a product manifest with output Artifact identity and provenance.

## Binding requirements

- The input binding is an existing immutable Artifact reference; no input data is fabricated or silently downloaded.
- The Cell template must match the exact registered Capability.
- The output contract must include the output data kind, supported media type, projected CRS and geometry types.
- Automatic execution is only permitted if the current autonomy policy produces automatic decisions and no approval is required.
- The registered checksum validator must be provided the Artifact Store used by execution.
- The current acceptance set does **not** assess geometry validity, cartographic quality, source licensing, freshness, or end-user usability. Those checks remain unassessed until dedicated validators exist.

## What this proves—and what it does not

The Blueprint expresses a customer outcome, planning and compilation resolve only registered capabilities, and the handoff reuses the immutable Recipe/Run lifecycle. The manifest is an internal assembled-product record. It is not yet a published map, web application, report, or customer delivery.

The example Blueprint is `examples/product_blueprints/road-access-buffer.json`.
