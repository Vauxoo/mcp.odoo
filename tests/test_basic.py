from odoo_mcp_multi import cli, config, server, utils


def test_imports():
    """Verify that all main modules can be imported successfully."""
    assert cli is not None
    assert server is not None
    assert config is not None
    assert utils is not None


def test_version():
    """Verify that the package has a version."""
    from odoo_mcp_multi import __version__

    assert __version__ == "0.2.2"
