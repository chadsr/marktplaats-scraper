from .listing import Listing


class ListingsError(Exception):
    """ListingsError provides an exception where listings can be recovered."""

    def __init__(
        self,
        listings: list[Listing],
        msg: str | None = None,
    ):
        self.msg = msg
        self.listings = listings

    def __str__(self):
        return f"Listings error: {self.msg}"


class ListingsInterrupt(ListingsError):
    """ListingsInterrupt provides an exception for keyboard interrupts, where listings can be recovered."""

    def __str__(self):
        return "Listings Interrupted"


class MPError(Exception):
    """MPError represents errors returned by Martkplaats."""

    def __init__(self, msg: str | None = None):
        self.msg = msg

    def __str__(self):
        return f"Marktplaats error: {self.msg}"


class CategoriesError(MPError):
    """CategoriesError is raised when no valid categories are found to crawl."""

    def __str__(self):
        return f"Categories error: {self.msg}"


class ForbiddenError(MPError):
    """ForbiddenError is raised when Marktplaats rate-limiting/blocking has been encountered."""

    def __str__(self):
        return f"Forbidden error: {self.msg}"


class NotFoundError(MPError):
    """NotFoundError is raised when a given URL returns a 404 error."""

    def __str__(self):
        return f"Not found error: {self.msg}"


class UnexpectedStatusCode(Exception):
    """UnexpectedStatusCode is raised when an unexpected HTTP response status code is encountered."""

    def __init__(self, status_code: int):
        self.status_code = status_code

    def __str__(self):
        return f"Unexpected status code: {self.status_code}"


class ElementNotFound(Exception):
    """ElementNotFound is raised when an expected element is not found."""

    def __init__(self, tag_name: str, attrs: dict[str, str] | None = None):
        self.tag_name = tag_name
        self.attrs = attrs

    def __str__(self):
        return f"Element not found with tag name {self.tag_name} and attributes: {self.attrs}"


class UnexpectedCategoryId(Exception):
    """UnexpectedCategoryId is raised when a page's category ID does not match the expected ID."""

    def __init__(self, got: int, exp: int):
        self.got = got
        self.exp = exp

    def __str__(self):
        return f"Unexpected category ID, expected {self.exp} but got {self.got}"


class ConfigNotFound(Exception):
    """ConfigNotFound is raised when a configuration file is not found at the provided path."""

    def __init__(self, path: str):
        self.path: str = path

    def __str__(self):
        return f"Config file not found at: {self.path}"


class EmptyDataFrameError(Exception):
    """EmptyDataFrameError is raised when a dataframe is empty/none when it should have data."""

    pass
