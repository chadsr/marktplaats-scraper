import os
from pyvirtualdisplay.display import Display


def has_display() -> bool:
    """Return true if a display is found."""
    if "DISPLAY" in os.environ:
        return True

    return False


def get_virtual_display(width: int = 1920, height: int = 1080) -> Display:
    """Return an initialised virtual display using xvfb."""
    display = Display(backend="xvfb", size=(width, height))
    display = display.start()
    return display
