"""Gemeinsame Fixtures (nur für HA-Tests; test_convert läuft ohne HA)."""

import pytest

pytest_plugins = []
try:  # HA-Testumgebung optional
    import pytest_homeassistant_custom_component  # noqa: F401

    pytest_plugins.append("pytest_homeassistant_custom_component")
    HAS_HA = True
except ImportError:
    HAS_HA = False


@pytest.fixture(autouse=True)
def _enable_custom(request):
    if HAS_HA and "hass" in request.fixturenames:
        request.getfixturevalue("enable_custom_integrations")
    yield
