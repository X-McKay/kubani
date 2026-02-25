"""
Computer Use MCP Server implementation.

Provides MCP tools for browser control via Playwright (headful Chromium).
"""

import base64
import contextlib
import logging
import os
import sys
from contextlib import asynccontextmanager
from typing import Any

from kubani.framework.mcp.server.health import HealthCheckManager
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from computer_mcp.models import ActionResult, ScreenshotResult

logger = logging.getLogger(__name__)

# Display dimensions from environment (default 1280x800)
DISPLAY_WIDTH = int(os.environ.get("DISPLAY_WIDTH", "1280"))
DISPLAY_HEIGHT = int(os.environ.get("DISPLAY_HEIGHT", "800"))

# Global browser state (set in lifespan)
_browser: Browser | None = None
_context: BrowserContext | None = None
_page: Page | None = None

# Global framework components
_health_manager: HealthCheckManager | None = None


@asynccontextmanager
async def lifespan(server: FastMCP):
    """MCP server lifespan - start and stop Playwright browser."""
    global _browser, _context, _page, _health_manager

    logger.info(
        "Starting Playwright browser (display: %dx%d)", DISPLAY_WIDTH, DISPLAY_HEIGHT
    )

    pw = await async_playwright().start()

    _browser = await pw.chromium.launch(
        headless=False,
        args=["--no-sandbox", "--disable-dev-shm-usage"],
    )
    _context = await _browser.new_context(
        viewport={"width": DISPLAY_WIDTH, "height": DISPLAY_HEIGHT},
    )
    _page = await _context.new_page()

    # Initialize health manager
    _health_manager = HealthCheckManager(version="0.1.0")

    async def check_browser():
        """Check if browser is still connected."""
        return _browser is not None and _browser.is_connected()

    _health_manager.register("browser", check_browser, timeout=5.0)

    logger.info("Playwright browser ready")

    yield

    # Cleanup
    logger.info("Shutting down Playwright browser")
    if _context:
        await _context.close()
    if _browser:
        await _browser.close()
    await pw.stop()

    _browser = None
    _context = None
    _page = None

    logger.info("Computer Use MCP Server shut down")


def create_server() -> FastMCP:
    """Create and configure the Computer Use MCP server."""
    # Get allowed hosts from environment or use defaults
    allowed_hosts_env = os.environ.get("MCP_ALLOWED_HOSTS", "")
    allowed_hosts = ["localhost:*", "127.0.0.1:*"]
    if allowed_hosts_env:
        allowed_hosts.extend(h.strip() for h in allowed_hosts_env.split(",") if h.strip())

    mcp = FastMCP(
        name="Computer Use MCP Server",
        instructions=(
            "Kubani Computer Use MCP Server. Provides browser control tools for "
            "agentic web interaction via Playwright. Use screenshot to observe the page, "
            "then click, type, scroll, and navigate to interact."
        ),
        lifespan=lifespan,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=allowed_hosts,
        ),
    )

    # =========================================================================
    # Browser Observation Tools
    # =========================================================================

    @mcp.tool()
    async def screenshot() -> ScreenshotResult:
        """
        Capture a screenshot of the current browser page.

        Returns:
            Screenshot as base64-encoded PNG with page dimensions, URL, and title.
        """
        assert _page is not None, "Browser not initialized"

        png_bytes = await _page.screenshot(full_page=False)
        image_base64 = base64.b64encode(png_bytes).decode("utf-8")

        return ScreenshotResult(
            image_base64=image_base64,
            width=DISPLAY_WIDTH,
            height=DISPLAY_HEIGHT,
            url=_page.url,
            title=await _page.title(),
        )

    # =========================================================================
    # Browser Action Tools
    # =========================================================================

    @mcp.tool()
    async def click(
        x: int,
        y: int,
        button: str = "left",
    ) -> ActionResult:
        """
        Click at the specified coordinates on the page.

        Args:
            x: X coordinate in pixels from the left edge.
            y: Y coordinate in pixels from the top edge.
            button: Mouse button to click ("left", "right", or "middle").

        Returns:
            Action result with success status.
        """
        assert _page is not None, "Browser not initialized"

        try:
            await _page.mouse.click(x, y, button=button)
            with contextlib.suppress(Exception):
                await _page.wait_for_load_state("domcontentloaded", timeout=3000)
            return ActionResult(
                success=True,
                message=f"Clicked ({x}, {y}) with {button} button",
                url=_page.url,
            )
        except Exception as e:
            return ActionResult(success=False, error=str(e), url=_page.url)

    @mcp.tool()
    async def type_text(text: str) -> ActionResult:
        """
        Type text into the currently focused element.

        Args:
            text: The text string to type.

        Returns:
            Action result with success status.
        """
        assert _page is not None, "Browser not initialized"

        try:
            await _page.keyboard.type(text, delay=30)
            return ActionResult(
                success=True,
                message=f"Typed {len(text)} characters",
                url=_page.url,
            )
        except Exception as e:
            return ActionResult(success=False, error=str(e), url=_page.url)

    @mcp.tool()
    async def key(combo: str) -> ActionResult:
        """
        Press a key or key combination.

        Args:
            combo: Key or combination to press (e.g., "Enter", "Control+a", "Backspace").

        Returns:
            Action result with success status.
        """
        assert _page is not None, "Browser not initialized"

        try:
            await _page.keyboard.press(combo)
            return ActionResult(
                success=True,
                message=f"Pressed {combo}",
                url=_page.url,
            )
        except Exception as e:
            return ActionResult(success=False, error=str(e), url=_page.url)

    @mcp.tool()
    async def scroll(
        direction: str = "down",
        amount: int = 3,
    ) -> ActionResult:
        """
        Scroll the page in the specified direction.

        Args:
            direction: Scroll direction ("up", "down", "left", or "right").
            amount: Number of scroll increments (each ~100px).

        Returns:
            Action result with success status.
        """
        assert _page is not None, "Browser not initialized"

        delta_map = {
            "down": (0, 100 * amount),
            "up": (0, -100 * amount),
            "right": (100 * amount, 0),
            "left": (-100 * amount, 0),
        }

        if direction not in delta_map:
            return ActionResult(
                success=False,
                error=f"Invalid direction: {direction}. Use up, down, left, or right.",
            )

        try:
            delta_x, delta_y = delta_map[direction]
            await _page.mouse.wheel(delta_x, delta_y)
            return ActionResult(
                success=True,
                message=f"Scrolled {direction} by {amount} increments",
                url=_page.url,
            )
        except Exception as e:
            return ActionResult(success=False, error=str(e), url=_page.url)

    @mcp.tool()
    async def navigate(url: str) -> ActionResult:
        """
        Navigate the browser to the specified URL.

        Args:
            url: URL to navigate to. "https://" is prepended if no protocol is specified.

        Returns:
            Action result with success status and the final URL.
        """
        assert _page is not None, "Browser not initialized"

        # Prepend protocol if missing
        if not url.startswith(("http://", "https://", "file://", "about:")):
            url = f"https://{url}"

        try:
            await _page.goto(url, wait_until="domcontentloaded", timeout=15000)
            return ActionResult(
                success=True,
                message=f"Navigated to {_page.url}",
                url=_page.url,
            )
        except Exception as e:
            return ActionResult(success=False, error=str(e), url=_page.url)

    # =========================================================================
    # Health Check
    # =========================================================================

    @mcp.tool()
    async def health() -> dict[str, Any]:
        """
        Check the health of the Computer Use MCP server.

        Returns:
            Health status including browser connection state.
        """
        if _health_manager:
            health_response = await _health_manager.check_all()
            return health_response.to_dict()

        # Fallback if health manager not initialized
        return {
            "status": "healthy" if _browser and _browser.is_connected() else "unhealthy",
            "browser_connected": _browser is not None and _browser.is_connected(),
        }

    return mcp


def main():
    """Entry point for the Computer Use MCP server."""
    import anyio
    from kubani.framework.mcp.server.transport import TransportConfig, run_server_async

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        stream=sys.stderr,
    )

    # Parse transport config from args
    config = TransportConfig.from_args()

    # Create the server
    mcp = create_server()

    # Run with transport config
    anyio.run(run_server_async, mcp, config)


if __name__ == "__main__":
    main()
