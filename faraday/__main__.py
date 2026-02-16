"""
Entry point for Project Faraday.
Detects whether to run CLI or GUI based on arguments and environment.
"""

import sys


def main():
    """Main entry point."""
    if len(sys.argv) > 1 and sys.argv[1] == "gui":
        try:
            from faraday.gui.main_window import main as gui_main
            gui_main()
        except ImportError:
            print("Error: GUI not available")
            sys.exit(1)
    else:
        from faraday.cli import main as cli_main
        sys.exit(cli_main())


if __name__ == "__main__":
    main()
