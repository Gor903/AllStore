import re

from app.models.store import SUBDOMAIN_PATTERN

_SUBDOMAIN = re.compile(SUBDOMAIN_PATTERN)


def subdomain_from_host(host: str | None, base_domain: str) -> str | None:
    """The storefront label of a Host header, or None when the host is not one of ours.

    Everything the caller controls is checked here: the host must be a single label under
    our own domain. A host we do not own resolves to nothing, so a forged Host header can
    only ever address a storefront that is public anyway.
    """
    if not host:
        return None
    # an IPv6 literal is never a storefront, and its colons would confuse the port split
    if host.startswith("["):
        return None
    name = host.strip().lower().split(":")[0]
    suffix = f".{base_domain.strip().lower()}"
    if not name.endswith(suffix):
        return None
    label = name[: -len(suffix)]
    # a dot left over means a deeper level (a.b.allstore.am), which we do not route
    if "." in label or not _SUBDOMAIN.match(label):
        return None
    return label
