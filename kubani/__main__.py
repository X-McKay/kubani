"""Allow running kubani as a module: python -m kubani"""

from kubani.cli.cli import main_cli

if __name__ == "__main__":
    main_cli()
