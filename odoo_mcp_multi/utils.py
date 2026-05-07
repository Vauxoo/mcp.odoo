"""Backward-compatible re-export shim.

All public symbols that were previously in utils.py can still be
imported from here.  New code should import from the specific module:

- ``odoo_mcp_multi.client``     — RPC clients and factory
- ``odoo_mcp_multi.exceptions`` — Custom exception classes
- ``odoo_mcp_multi.parsers``    — Argument parsing utilities
- ``odoo_mcp_multi.version``    — Version detection and protocol enum
"""

from odoo_mcp_multi.client import *  # noqa: F401,F403
from odoo_mcp_multi.exceptions import *  # noqa: F401,F403
from odoo_mcp_multi.parsers import *  # noqa: F401,F403
from odoo_mcp_multi.version import *  # noqa: F401,F403
