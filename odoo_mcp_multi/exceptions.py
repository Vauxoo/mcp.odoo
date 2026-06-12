"""Custom exceptions for Odoo RPC communication.

Separated from the client module to avoid circular imports —
both clients and operations need to reference these exceptions.
"""


class OdooConnectionError(Exception):
    """Exception raised for Odoo connection failures."""

    pass


class OdooSSLVerificationError(OdooConnectionError):
    """Exception raised specifically for Odoo SSL certificate validation and verification failures."""

    pass


class OdooAuthenticationError(Exception):
    """Exception raised for authentication failures."""

    pass


class OdooExecutionError(Exception):
    """Exception raised for method execution failures."""

    pass
