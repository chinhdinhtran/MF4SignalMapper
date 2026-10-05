from __future__ import annotations

import sys


def main() -> int:
    if "--cli" in sys.argv:
        from mf4_mapper.cli import main as cli_main
        args = [arg for arg in sys.argv[1:] if arg != "--cli"]
        sys.argv = [sys.argv[0], *args]
        return cli_main()

    from mf4_mapper.gui_main import run_gui
    return run_gui()


if __name__ == "__main__":
    raise SystemExit(main())
