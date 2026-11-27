

def test_requested_autonomy_mode_is_part_of_plan_identity():
    item = blueprint()
    automatic = plan_product_blueprint(item, capabilities=CapabilityRegistry())
    guided = plan_product_blueprint(
        item, capabilities=CapabilityRegistry(), requested_mode="guided"
    )
    assert guided["plan_fingerprint"] != automatic["plan_fingerprint"]
    assert all(
        decision["mode"] == "guided"
        for decision in guided["autonomy_decisions"]
    )
