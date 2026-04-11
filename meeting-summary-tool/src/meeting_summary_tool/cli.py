"""CLI entrypoint for the meeting summary tool."""

from __future__ import annotations

from collections.abc import Sequence


def main(argv: Sequence[str] | None = None) -> int:
    """Run the minimal CLI entrypoint.

    The full argument parser is added in a follow-up issue. For now this
    function exists so the package can expose a stable entrypoint.
    """

    _ = argv
    print("meeting-summary-tool CLI scaffold is ready.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
