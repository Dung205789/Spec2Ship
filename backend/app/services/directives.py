from __future__ import annotations


def parse_spec2ship_directives(ticket_text: str) -> tuple[str | None, dict[str, str]]:
    """Parse a small, copy/paste-friendly directive block from ticket_text.

    Supported format (put near the top of the ticket):

        #spec2ship: swebench_eval
        key=value
        key=value

    Lines starting with # are treated as comments, except "#spec2ship:".
    """

    mode: str | None = None
    cfg: dict[str, str] = {}

    if not ticket_text:
        return None, cfg

    for raw in ticket_text.splitlines()[:60]:
        line = (raw or "").strip()
        if not line:
            continue

        low = line.lower()
        if low.startswith("#spec2ship:"):
            mode = line.split(":", 1)[1].strip().lower() or None
            continue

        # regular comments
        if line.startswith("#"):
            continue

        if "=" in line:
            k, v = line.split("=", 1)
            k = k.strip().lower()
            v = v.strip()
            if k:
                cfg[k] = v

    return mode, cfg
