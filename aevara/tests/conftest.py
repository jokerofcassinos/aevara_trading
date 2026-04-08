# @module: aevara.tests.conftest
# @deps: None
# @status: IMPLEMENTED
# @last_update: 2026-04-06
# @summary: Pytest conftest - adiciona aevara root ao path.

import sys
import os

# Add aevara root to path for all tests
aevara_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if aevara_root not in sys.path:
    sys.path.insert(0, aevara_root)
