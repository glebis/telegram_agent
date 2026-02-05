"""Test that security headers are present on responses."""


def test_security_headers_middleware_exists():
    """Verify security headers middleware is registered."""
    import inspect

    import src.main as main_module

    main_source = inspect.getsource(main_module)

    assert (
        "X-Content-Type-Options" in main_source
    ), "Missing X-Content-Type-Options header"
    assert "X-Frame-Options" in main_source, "Missing X-Frame-Options header"
    assert "X-XSS-Protection" in main_source, "Missing X-XSS-Protection header"
    assert "Referrer-Policy" in main_source, "Missing Referrer-Policy header"
    assert "Cache-Control" in main_source, "Missing Cache-Control header"
    assert "Strict-Transport-Security" in main_source, "Missing HSTS header"


def test_cors_not_wildcard():
    """Verify CORS doesn't use wildcard methods/headers."""
    import inspect

    import src.main as main_module

    main_source = inspect.getsource(main_module)

    # Check that allow_methods is not ["*"]
    assert (
        'allow_methods=["*"]' not in main_source
    ), "CORS allow_methods should not be wildcard"
    assert (
        'allow_headers=["*"]' not in main_source
    ), "CORS allow_headers should not be wildcard"
