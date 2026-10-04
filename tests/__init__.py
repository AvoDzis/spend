import os
import tempfile

# `spend month` / `spend list` import the phone inbox first; keep every test away from the real one.
# Tests that need an inbox set SPEND_INBOX themselves.
os.environ["SPEND_INBOX"] = os.path.join(tempfile.gettempdir(), "spend-tests-no-inbox", "inbox.txt")
