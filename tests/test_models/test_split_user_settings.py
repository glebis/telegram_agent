"""Tests for split user_settings bounded-context models.

Issue #222: UserSettings mixes voice, accountability, privacy, life-weeks concerns.
Multiple bounded contexts mutate same row. Solution: separate tables per context.
"""

from sqlalchemy import BigInteger, Boolean, Integer, String, Text


class TestVoiceSettingsModel:
    """VoiceSettings should own voice synthesis configuration."""

    def test_importable(self):
        from src.models.voice_settings import VoiceSettings

        assert VoiceSettings is not None

    def test_tablename(self):
        from src.models.voice_settings import VoiceSettings

        assert VoiceSettings.__tablename__ == "voice_settings"

    def test_has_user_id_pk(self):
        from src.models.voice_settings import VoiceSettings

        col = VoiceSettings.__table__.columns["user_id"]
        assert col.primary_key
        assert isinstance(col.type, BigInteger)

    def test_has_voice_enabled(self):
        from src.models.voice_settings import VoiceSettings

        col = VoiceSettings.__table__.columns["voice_enabled"]
        assert isinstance(col.type, Boolean)

    def test_has_voice_model(self):
        from src.models.voice_settings import VoiceSettings

        col = VoiceSettings.__table__.columns["voice_model"]
        assert isinstance(col.type, String)

    def test_has_emotion_style(self):
        from src.models.voice_settings import VoiceSettings

        col = VoiceSettings.__table__.columns["emotion_style"]
        assert isinstance(col.type, String)

    def test_has_response_mode(self):
        from src.models.voice_settings import VoiceSettings

        col = VoiceSettings.__table__.columns["response_mode"]
        assert isinstance(col.type, String)

    def test_defaults(self):
        from src.models.voice_settings import VoiceSettings

        vs = VoiceSettings(user_id=123)
        assert vs.voice_enabled is True
        assert vs.voice_model == "diana"
        assert vs.emotion_style == "cheerful"
        assert vs.response_mode == "smart"

    def test_has_timestamps(self):
        from src.models.voice_settings import VoiceSettings

        assert hasattr(VoiceSettings, "created_at")
        assert hasattr(VoiceSettings, "updated_at")


class TestAccountabilityProfileModel:
    """AccountabilityProfile should own partner personality and check-in config."""

    def test_importable(self):
        from src.models.accountability_profile import AccountabilityProfile

        assert AccountabilityProfile is not None

    def test_tablename(self):
        from src.models.accountability_profile import AccountabilityProfile

        assert AccountabilityProfile.__tablename__ == "accountability_profiles"

    def test_has_user_id_pk(self):
        from src.models.accountability_profile import AccountabilityProfile

        col = AccountabilityProfile.__table__.columns["user_id"]
        assert col.primary_key
        assert isinstance(col.type, BigInteger)

    def test_has_partner_personality(self):
        from src.models.accountability_profile import AccountabilityProfile

        col = AccountabilityProfile.__table__.columns["partner_personality"]
        assert isinstance(col.type, String)

    def test_has_partner_voice_override(self):
        from src.models.accountability_profile import AccountabilityProfile

        col = AccountabilityProfile.__table__.columns["partner_voice_override"]
        assert col.nullable

    def test_has_check_in_time(self):
        from src.models.accountability_profile import AccountabilityProfile

        col = AccountabilityProfile.__table__.columns["check_in_time"]
        assert isinstance(col.type, String)

    def test_has_struggle_threshold(self):
        from src.models.accountability_profile import AccountabilityProfile

        col = AccountabilityProfile.__table__.columns["struggle_threshold"]
        assert isinstance(col.type, Integer)

    def test_has_celebration_style(self):
        from src.models.accountability_profile import AccountabilityProfile

        col = AccountabilityProfile.__table__.columns["celebration_style"]
        assert isinstance(col.type, String)

    def test_has_auto_adjust_personality(self):
        from src.models.accountability_profile import AccountabilityProfile

        col = AccountabilityProfile.__table__.columns["auto_adjust_personality"]
        assert isinstance(col.type, Boolean)

    def test_has_check_in_times(self):
        from src.models.accountability_profile import AccountabilityProfile

        col = AccountabilityProfile.__table__.columns["check_in_times"]
        assert isinstance(col.type, Text)

    def test_has_reminder_style(self):
        from src.models.accountability_profile import AccountabilityProfile

        col = AccountabilityProfile.__table__.columns["reminder_style"]
        assert isinstance(col.type, String)

    def test_has_timezone(self):
        from src.models.accountability_profile import AccountabilityProfile

        col = AccountabilityProfile.__table__.columns["timezone"]
        assert isinstance(col.type, String)

    def test_defaults(self):
        from src.models.accountability_profile import AccountabilityProfile

        ap = AccountabilityProfile(user_id=123)
        assert ap.partner_personality == "supportive"
        assert ap.partner_voice_override is None
        assert ap.check_in_time == "19:00"
        assert ap.struggle_threshold == 3
        assert ap.celebration_style == "moderate"
        assert ap.auto_adjust_personality is False
        assert ap.reminder_style == "gentle"
        assert ap.timezone == "UTC"

    def test_has_timestamps(self):
        from src.models.accountability_profile import AccountabilityProfile

        assert hasattr(AccountabilityProfile, "created_at")
        assert hasattr(AccountabilityProfile, "updated_at")


class TestPrivacySettingsModel:
    """PrivacySettings should own privacy/GDPR configuration."""

    def test_importable(self):
        from src.models.privacy_settings import PrivacySettings

        assert PrivacySettings is not None

    def test_tablename(self):
        from src.models.privacy_settings import PrivacySettings

        assert PrivacySettings.__tablename__ == "privacy_settings"

    def test_has_user_id_pk(self):
        from src.models.privacy_settings import PrivacySettings

        col = PrivacySettings.__table__.columns["user_id"]
        assert col.primary_key
        assert isinstance(col.type, BigInteger)

    def test_has_privacy_level(self):
        from src.models.privacy_settings import PrivacySettings

        col = PrivacySettings.__table__.columns["privacy_level"]
        assert isinstance(col.type, String)

    def test_has_data_retention(self):
        from src.models.privacy_settings import PrivacySettings

        col = PrivacySettings.__table__.columns["data_retention"]
        assert isinstance(col.type, String)

    def test_has_health_data_consent(self):
        from src.models.privacy_settings import PrivacySettings

        col = PrivacySettings.__table__.columns["health_data_consent"]
        assert isinstance(col.type, Boolean)

    def test_defaults(self):
        from src.models.privacy_settings import PrivacySettings

        ps = PrivacySettings(user_id=123)
        assert ps.privacy_level == "private"
        assert ps.data_retention == "1_year"
        assert ps.health_data_consent is False

    def test_has_timestamps(self):
        from src.models.privacy_settings import PrivacySettings

        assert hasattr(PrivacySettings, "created_at")
        assert hasattr(PrivacySettings, "updated_at")


class TestLifeWeeksSettingsModel:
    """LifeWeeksSettings should own life-weeks visualization config."""

    def test_importable(self):
        from src.models.life_weeks_settings import LifeWeeksSettings

        assert LifeWeeksSettings is not None

    def test_tablename(self):
        from src.models.life_weeks_settings import LifeWeeksSettings

        assert LifeWeeksSettings.__tablename__ == "life_weeks_settings"

    def test_has_user_id_pk(self):
        from src.models.life_weeks_settings import LifeWeeksSettings

        col = LifeWeeksSettings.__table__.columns["user_id"]
        assert col.primary_key
        assert isinstance(col.type, BigInteger)

    def test_has_date_of_birth(self):
        from src.models.life_weeks_settings import LifeWeeksSettings

        col = LifeWeeksSettings.__table__.columns["date_of_birth"]
        assert col.nullable

    def test_has_life_weeks_enabled(self):
        from src.models.life_weeks_settings import LifeWeeksSettings

        col = LifeWeeksSettings.__table__.columns["life_weeks_enabled"]
        assert isinstance(col.type, Boolean)

    def test_has_life_weeks_day(self):
        from src.models.life_weeks_settings import LifeWeeksSettings

        col = LifeWeeksSettings.__table__.columns["life_weeks_day"]
        assert isinstance(col.type, Integer)
        assert col.nullable

    def test_has_life_weeks_time(self):
        from src.models.life_weeks_settings import LifeWeeksSettings

        col = LifeWeeksSettings.__table__.columns["life_weeks_time"]
        assert isinstance(col.type, String)

    def test_has_life_weeks_reply_destination(self):
        from src.models.life_weeks_settings import LifeWeeksSettings

        col = LifeWeeksSettings.__table__.columns["life_weeks_reply_destination"]
        assert isinstance(col.type, String)

    def test_has_life_weeks_custom_path(self):
        from src.models.life_weeks_settings import LifeWeeksSettings

        col = LifeWeeksSettings.__table__.columns["life_weeks_custom_path"]
        assert col.nullable

    def test_defaults(self):
        from src.models.life_weeks_settings import LifeWeeksSettings

        lw = LifeWeeksSettings(user_id=123)
        assert lw.life_weeks_enabled is False
        assert lw.date_of_birth is None
        assert lw.life_weeks_day is None
        assert lw.life_weeks_time == "09:00"
        assert lw.life_weeks_reply_destination == "daily_note"
        assert lw.life_weeks_custom_path is None

    def test_has_timestamps(self):
        from src.models.life_weeks_settings import LifeWeeksSettings

        assert hasattr(LifeWeeksSettings, "created_at")
        assert hasattr(LifeWeeksSettings, "updated_at")


class TestModelsExportedFromInit:
    """New models should be importable from src.models."""

    def test_voice_settings_in_init(self):
        from src.models import VoiceSettings

        assert VoiceSettings is not None

    def test_accountability_profile_in_init(self):
        from src.models import AccountabilityProfile

        assert AccountabilityProfile is not None

    def test_privacy_settings_in_init(self):
        from src.models import PrivacySettings

        assert PrivacySettings is not None

    def test_life_weeks_settings_in_init(self):
        from src.models import LifeWeeksSettings

        assert LifeWeeksSettings is not None


class TestUserSettingsBackwardCompat:
    """Original UserSettings model should still exist for migration compat."""

    def test_original_still_importable(self):
        from src.models.user_settings import UserSettings

        assert UserSettings is not None

    def test_original_table_unchanged(self):
        from src.models.user_settings import UserSettings

        assert UserSettings.__tablename__ == "user_settings"
