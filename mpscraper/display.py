import os

from pyvirtualdisplay.display import Display


def has_display() -> bool:
    """Return true if a display is found."""
    return "DISPLAY" in os.environ


def get_virtual_display(width: int = 1920, height: int = 1080) -> Display:
    """Return an initialised virtual display using xvfb."""
    return Display(backend="xvfb", size=(width, height)).start()
