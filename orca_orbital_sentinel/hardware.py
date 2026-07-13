"""!
@file hardware.py
@brief Output sinks for the compact renderer: desktop preview or a real panel.
@details
    The compact renderer produces a small Surface; a DisplaySink decides where it
    goes. `PreviewSink` scales it into a desktop window so the small-screen layout
    can be developed without hardware. `SpiPanelSink` pushes the same buffer to a
    physical SPI display (ST7789/ILI9341 TFT or an SSD1306 OLED) via the optional
    `luma` libraries; it is imported lazily so the rest of the app never depends on
    hardware packages.

    Select a sink with the ORCA_DISPLAY environment variable: "preview" (default)
    or "spi".

    This module is imported, not executed directly.
"""

import os

import pygame

from . import config


class PreviewSink:
    """! @brief Scales the panel Surface into a resizable desktop window."""

    def __init__(self, width, height, scale):
        """! @brief Open the preview window.
            @param width Panel width in pixels.
            @param height Panel height in pixels.
            @param scale Integer upscale factor for the desktop preview.
        """
        pygame.init()
        pygame.display.set_caption("ORCA // LCD preview")
        self.size = (width * scale, height * scale)
        self.window = pygame.display.set_mode(self.size)

    def show(self, surface):
        """! @brief Nearest-neighbour upscale the panel buffer and present it."""
        pygame.transform.scale(surface, self.size, self.window)
        pygame.display.flip()

    def close(self):
        """! @brief Tear down the window."""
        pygame.quit()


class SpiPanelSink:
    """! @brief Push the panel Surface to a physical SPI display via luma.

    @details Hardware-only; requires `luma.lcd` (TFT) or `luma.oled` (OLED) and a
        wired panel. Not exercised in CI. Typical ST7789 wiring (Raspberry Pi):
            VCC->3V3, GND->GND, SCL->SCLK(GPIO11), SDA->MOSI(GPIO10),
            RES->GPIO25, DC->GPIO24, CS->CE0(GPIO8), BLK->3V3.
    """

    def __init__(self, width, height):
        """! @brief Initialise the SPI device (imports luma lazily).
            @param width Panel width in pixels.
            @param height Panel height in pixels.
        """
        # Lazy imports: absent on a normal desktop, and that must not break import.
        from luma.core.interface.serial import spi          # noqa: WPS433
        from luma.lcd.device import st7789                   # noqa: WPS433

        self.width, self.height = width, height
        serial = spi(port=0, device=0, gpio_DC=24, gpio_RST=25)
        self.device = st7789(serial, width=width, height=height, rotate=0)

    def show(self, surface):
        """! @brief Convert the Surface to a PIL image and blit to the panel."""
        from PIL import Image                               # noqa: WPS433
        raw = pygame.image.tobytes(surface, "RGB")
        image = Image.frombytes("RGB", (self.width, self.height), raw)
        self.device.display(image)

    def close(self):
        """! @brief Best-effort clear of the panel."""
        try:
            self.device.clear()
        except Exception:                                   # noqa: BLE001
            pass


def make_sink():
    """! @brief Build the sink selected by ORCA_DISPLAY (preview|spi).
        @return A sink exposing show(surface) and close().
    """
    mode = os.environ.get("ORCA_DISPLAY", "preview").lower()
    if mode == "spi":
        return SpiPanelSink(config.SMALL_W, config.SMALL_H)
    return PreviewSink(config.SMALL_W, config.SMALL_H, config.SMALL_PREVIEW_SCALE)
