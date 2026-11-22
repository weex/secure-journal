"""Local development entry: HTTP journal on 127.0.0.1:8000.

Create a password record first:

    python -m journal_app.init --password 'a long mixed passphrase'
    JOURNAL_DEV=1 python -m journal_app
"""

from journal_app.web import main

if __name__ == "__main__":
    main()
