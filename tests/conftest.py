"""Root test configuration.

Sets environment variables required by all tests before any test module
is imported or any singleton is initialised.

Real credentials live at ``~/cred/repomgr/.env``.  The
values below are stubs sufficient for unit tests that do not call any
external service.
"""

import os

# Required by SampleParams._load_common_params() via _load_secret().
os.environ.setdefault("SAMPLE_API_KEY", "test-api-key-do-not-use-in-prod")
