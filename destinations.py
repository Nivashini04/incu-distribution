
DESTINATIONS = {
    "mock-community": {
        "allow_self_promotion": False,
        "allow_links": False,
        "require_ai_disclosure": True,
        "connector_type": "mock",
    },
    "open-community": {
        "allow_self_promotion": True,
        "allow_links": True,
        "require_ai_disclosure": False,
        "connector_type": "mock",
    },
    "assisted-community": {
        "allow_self_promotion": True,
        "allow_links": True,
        "require_ai_disclosure": False,
        "connector_type": "assisted",
    },
}
