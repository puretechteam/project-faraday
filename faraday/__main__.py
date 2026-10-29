"""
Entry point for Project Faraday.
Detects whether to run CLI or GUI based on arguments and environment.

    faraday gui            the desktop app
    faraday <command>      the command-line interface
"""

import sys


def main():
    """Main entry point."""
    if len(sys.argv) > 1 and sys.argv[1] == "gui":
        try:
            from faraday.qt.app import main as qt_main
        except ImportError as e:
            print(f"Error: GUI not available ({e}). Install it with: pip install -e .")
            sys.exit(1)
        sys.exit(qt_main([sys.argv[0]]))
    else:
        from faraday.cli import main as cli_main
        sys.exit(cli_main())


if __name__ == "__main__":
    main()
