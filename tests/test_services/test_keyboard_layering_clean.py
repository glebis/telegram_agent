"""Verify that srs_service and accountability_scheduler no longer need layering exceptions."""


class TestKeyboardLayeringExceptionsCleaned:
    """The telegram_keyboards exceptions must be removed from ALLOWED_EXCEPTIONS."""

    def test_srs_service_exception_removed(self):
        """srs_service.py must NOT appear in ALLOWED_EXCEPTIONS for telegram_keyboards."""
        from tests.test_import_layering import ALLOWED_EXCEPTIONS

        srs_exceptions = [
            (f, m)
            for f, m in ALLOWED_EXCEPTIONS
            if f == "services/srs_service.py" and "telegram_keyboards" in m
        ]
        assert (
            srs_exceptions == []
        ), f"srs_service.py still has a telegram_keyboards exception: {srs_exceptions}"

    def test_accountability_scheduler_exception_removed(self):
        """accountability_scheduler.py must NOT appear in ALLOWED_EXCEPTIONS for telegram_keyboards."""
        from tests.test_import_layering import ALLOWED_EXCEPTIONS

        sched_exceptions = [
            (f, m)
            for f, m in ALLOWED_EXCEPTIONS
            if f == "services/accountability_scheduler.py" and "telegram_keyboards" in m
        ]
        assert (
            sched_exceptions == []
        ), f"accountability_scheduler.py still has a telegram_keyboards exception: {sched_exceptions}"
