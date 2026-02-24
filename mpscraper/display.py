import os

from xvfbwrapper import Xvfb


def has_display() -> bool:
    """Return true if a display is found."""
    return "DISPLAY" in os.environ


def get_virtual_display(width: int = 1920, height: int = 1080) -> Xvfb:
    """Return an initialised virtual display using xvfb."""
    display = Xvfb(width=width, height=height)
    display.start()
    return display


def is_display_running(display: Xvfb) -> bool:
    """Check if the virtual display is running."""
    return display.proc is not None  # pyright: ignore[reportUnknownMemberType, reportAttributeAccessIssue]
