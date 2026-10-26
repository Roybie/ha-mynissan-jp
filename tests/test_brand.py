"""Check Home Assistant serves the integration's own brand icon."""

from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_integration
from homeassistant.setup import async_setup_component


async def test_brand_icon_served(hass: HomeAssistant, hass_client) -> None:
    integration = await async_get_integration(hass, "mynissan_jp")
    assert integration.has_branding
    assert await async_setup_component(hass, "brands", {})
    client = await hass_client()
    for image in ("icon.png", "dark_icon@2x.png", "logo@2x.png"):
        resp = await client.get(f"/api/brands/integration/mynissan_jp/{image}")
        assert resp.status == 200, image
        body = await resp.read()
        assert body.startswith(b"\x89PNG")
