"""Windowless launcher used by "Launch on startup" when running from source.

Living at the repo root puts the project on sys.path no matter which working
directory Windows starts us in.
"""

from whisperfree.app import main


if __name__ == "__main__":
    main()
