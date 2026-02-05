"""Test GDPR compliance features."""


def test_privacy_commands_exist():
    """Verify privacy command handlers are importable."""
    from src.bot.handlers.privacy_commands import (
        deletedata_command,
        handle_gdpr_callback,
        mydata_command,
        privacy_command,
    )

    assert callable(privacy_command)
    assert callable(mydata_command)
    assert callable(deletedata_command)
    assert callable(handle_gdpr_callback)


def test_privacy_commands_registered():
    """Verify privacy commands are registered in bot handlers."""
    import inspect

    from src.bot import bot as bot_module

    source = inspect.getsource(bot_module)

    assert "privacy_command" in source, "/privacy command not registered"
    assert "mydata_command" in source, "/mydata command not registered"
    assert "deletedata_command" in source, "/deletedata command not registered"


def test_user_model_has_consent_fields():
    """Verify User model has GDPR consent fields."""
    from src.models.user import User

    # Check that the model has consent fields
    assert hasattr(User, "consent_given"), "User model missing consent_given field"
    assert hasattr(
        User, "consent_given_at"
    ), "User model missing consent_given_at field"


def test_user_settings_has_health_consent():
    """Verify UserSettings model has health data consent field."""
    from src.models.user_settings import UserSettings

    assert hasattr(
        UserSettings, "health_data_consent"
    ), "UserSettings model missing health_data_consent field"


def test_data_retention_service_exists():
    """Verify data retention service is importable."""
    from src.services.data_retention_service import (
        RETENTION_PERIODS,
        enforce_data_retention,
        run_periodic_retention,
    )

    assert callable(enforce_data_retention)
    assert callable(run_periodic_retention)
    assert "1_month" in RETENTION_PERIODS
    assert "forever" in RETENTION_PERIODS
    assert RETENTION_PERIODS["forever"] is None


def test_audit_log_exists():
    """Verify audit logging is available."""
    from src.utils.audit_log import audit_log, get_audit_logger

    assert callable(audit_log)
    assert callable(get_audit_logger)


def test_encryption_utility_exists():
    """Verify field encryption utility is available."""
    from src.utils.encryption import decrypt_field, encrypt_field, is_encrypted

    assert callable(encrypt_field)
    assert callable(decrypt_field)
    assert callable(is_encrypted)
