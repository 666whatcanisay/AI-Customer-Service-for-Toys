from channel_engine.catalog_scope import canonical_catalog_platform


def test_pdd_channel_aliases_use_the_ai_cs_catalog_identity() -> None:
    assert canonical_catalog_platform("pdd") == "pinduoduo"
    assert canonical_catalog_platform("PDD") == "pinduoduo"
    assert canonical_catalog_platform("拼多多") == "pinduoduo"
    assert canonical_catalog_platform("pinduoduo") == "pinduoduo"


def test_unknown_platform_identity_is_preserved_after_trimming() -> None:
    assert canonical_catalog_platform("  future-platform  ") == "future-platform"
