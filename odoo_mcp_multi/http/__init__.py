"""Authenticated HTTP transport for the Odoo MCP server.

Everything in this package is only imported when ``odoo-mcp serve`` runs, so
the stdio entry point stays free of Starlette, uvicorn and cryptography.
"""
