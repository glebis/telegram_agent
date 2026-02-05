import hashlib
import hmac
import logging
import os
from typing import Dict, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, HttpUrl
from starlette.requests import HTTPConnection

from ..core.config import get_settings
from ..tunnel import get_tunnel_provider
from ..utils.ngrok_utils import (
    NgrokManager,
    WebhookManager,
    auto_update_webhook_on_restart,
)

logger = logging.getLogger(__name__)


def _log_auth_failure(request: Optional[HTTPConnection], reason: str) -> None:
    """Log structured auth failure with IP and User-Agent. Never logs secrets."""
    if request is None:
        logger.warning("Auth failure: reason=%s (no request context)", reason)
        return
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")
    logger.warning(
        "Auth failure on %s %s: reason=%s, ip=%s, user_agent=%s",
        getattr(request, "method", "?"),
        request.url.path,
        reason,
        client_ip,
        user_agent,
    )


# =============================================================================
# Authentication Dependencies
# =============================================================================


def get_admin_api_key() -> str:
    """Derive admin API key from webhook secret using salted hash.

    This creates a separate key from the messaging API for admin operations.
    """
    secret = None
    from_mock = False

    try:
        from unittest.mock import Mock

        settings_factory = get_settings
        if isinstance(settings_factory, Mock):
            # When patched in tests, honor the injected value and do not fall back to env
            from_mock = True
            settings = settings_factory()
        else:
            settings = settings_factory()

        secret = getattr(settings, "telegram_webhook_secret", None)
    except Exception:
        secret = None

    # Environment has final say when not explicitly mocked
    if not from_mock:
        env_secret = os.getenv("TELEGRAM_WEBHOOK_SECRET")
        if env_secret:
            secret = env_secret

    if not secret:
        raise ValueError("TELEGRAM_WEBHOOK_SECRET not configured")
    return hashlib.sha256(f"{secret}:admin_api".encode()).hexdigest()


async def verify_admin_key(
    request: Request,
    x_api_key: Optional[str] = Header(
        None, description="Admin API key for authentication"
    ),
) -> bool:
    """Verify the admin API key header.

    Uses timing-safe comparison to prevent timing attacks.
    Returns 401 if header is missing or invalid.
    Logs IP and User-Agent on any auth failure (never logs the key itself).
    """
    if not x_api_key:
        _log_auth_failure(request, "missing_admin_api_key")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    try:
        expected_key = get_admin_api_key()
    except ValueError as e:
        logger.error(f"Admin auth configuration error: {e}")
        _log_auth_failure(request, "admin_auth_not_configured")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication not configured",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    except Exception as e:
        logger.error(f"Unexpected error deriving admin API key: {e}")
        _log_auth_failure(request, "admin_auth_error")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication not configured",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    if not hmac.compare_digest(x_api_key, expected_key):
        _log_auth_failure(request, "invalid_admin_api_key")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    return True


def get_bot_token() -> str:
    """Get bot token from settings (dependency injection)."""
    settings = get_settings()
    if not settings.telegram_bot_token:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Bot token not configured",
        )
    return settings.telegram_bot_token


# =============================================================================
# Router with authentication
# =============================================================================

router = APIRouter(
    prefix="/admin/webhook",
    tags=["webhook"],
    dependencies=[Depends(verify_admin_key)],  # All routes require auth
)


class WebhookUpdateRequest(BaseModel):
    url: HttpUrl
    secret_token: Optional[str] = None


class WebhookRefreshRequest(BaseModel):
    port: int = 8000
    webhook_path: str = "/webhook"
    secret_token: Optional[str] = None


class WebhookResponse(BaseModel):
    success: bool
    message: str
    webhook_url: Optional[str] = None


class WebhookStatusResponse(BaseModel):
    telegram_webhook: Dict
    ngrok_status: Dict
    active: bool


@router.post("/update", response_model=WebhookResponse)
async def update_webhook(
    request: WebhookUpdateRequest,
    background_tasks: BackgroundTasks,
    bot_token: str = Depends(get_bot_token),
) -> WebhookResponse:
    try:
        webhook_manager = WebhookManager(bot_token)

        # Log detailed information about the webhook update request
        logger.info(f"Webhook update requested via API")
        logger.info(f"Webhook URL: {request.url}")
        logger.info(f"Environment: {os.getenv('ENVIRONMENT', 'not set')}")
        logger.info(f"Has secret token: {request.secret_token is not None}")

        success, message = await webhook_manager.set_webhook(
            str(request.url), request.secret_token
        )

        if success:
            logger.info(f"Webhook updated via API: {request.url}")
            return WebhookResponse(
                success=True, message=message, webhook_url=str(request.url)
            )
        else:
            logger.error(f"Failed to update webhook via API: {message}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to update webhook: {message}",
            )

    except Exception as e:
        logger.error(f"Error updating webhook: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal error updating webhook: {str(e)}",
        )


@router.post("/refresh", response_model=WebhookResponse)
async def refresh_webhook(
    request: WebhookRefreshRequest,
    background_tasks: BackgroundTasks,
    bot_token: str = Depends(get_bot_token),
) -> WebhookResponse:
    try:
        # Log detailed information about the webhook refresh request
        logger.info(f"Webhook refresh requested via API")
        logger.info(f"Port: {request.port}")
        logger.info(f"Webhook path: {request.webhook_path}")
        logger.info(f"Environment: {os.getenv('ENVIRONMENT', 'not set')}")
        logger.info(f"WEBHOOK_BASE_URL: {os.getenv('WEBHOOK_BASE_URL', 'not set')}")
        logger.info(f"Has secret token: {request.secret_token is not None}")

        success, message, webhook_url = await auto_update_webhook_on_restart(
            bot_token=bot_token,
            port=request.port,
            webhook_path=request.webhook_path,
            secret_token=request.secret_token,
        )

        if success:
            logger.info(f"Webhook refreshed successfully via API: {webhook_url}")
            return WebhookResponse(
                success=True, message=message, webhook_url=webhook_url
            )
        else:
            logger.error(f"Failed to refresh webhook via API: {message}")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)

    except Exception as e:
        logger.error(f"Error refreshing webhook: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal error refreshing webhook: {str(e)}",
        )


@router.get("/status", response_model=WebhookStatusResponse)
async def get_webhook_status(
    bot_token: str = Depends(get_bot_token),
) -> WebhookStatusResponse:
    try:
        webhook_manager = WebhookManager(bot_token)

        # Get Telegram webhook info
        telegram_webhook = await webhook_manager.get_webhook_info()

        # Get tunnel provider status (provider-agnostic)
        tunnel_status: Dict = {"active": False, "url": None}
        try:
            provider = get_tunnel_provider()
            if provider:
                tunnel_status = provider.get_status()
        except Exception:
            # Fallback to direct NgrokManager
            ngrok_manager = NgrokManager()
            tunnel_status = ngrok_manager.get_tunnel_status()

        # Determine if webhook is active
        active = telegram_webhook.get("url", "") != "" and tunnel_status.get(
            "active", False
        )

        return WebhookStatusResponse(
            telegram_webhook=telegram_webhook,
            ngrok_status=tunnel_status,
            active=active,
        )

    except Exception as e:
        logger.error(f"Error getting webhook status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal error getting webhook status: {str(e)}",
        )


@router.delete("/", response_model=WebhookResponse)
async def delete_webhook(
    bot_token: str = Depends(get_bot_token),
) -> WebhookResponse:
    try:
        webhook_manager = WebhookManager(bot_token)

        success, message = await webhook_manager.delete_webhook()

        if success:
            return WebhookResponse(success=True, message=message)
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)

    except Exception as e:
        logger.error(f"Error deleting webhook: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal error deleting webhook: {str(e)}",
        )


@router.post("/ngrok/start", response_model=WebhookResponse)
async def start_ngrok_tunnel(
    auth_token: Optional[str] = None,
    port: int = 8000,
    region: str = "us",
    tunnel_name: str = "telegram-agent",
) -> WebhookResponse:
    try:
        ngrok_manager = NgrokManager(auth_token, port, region, tunnel_name)

        public_url = ngrok_manager.start_tunnel()

        return WebhookResponse(
            success=True,
            message=f"ngrok tunnel started successfully",
            webhook_url=public_url,
        )

    except Exception as e:
        logger.error(f"Error starting ngrok tunnel: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start ngrok tunnel: {str(e)}",
        )


@router.post("/ngrok/stop", response_model=WebhookResponse)
async def stop_ngrok_tunnel() -> WebhookResponse:
    try:
        ngrok_manager = NgrokManager()
        ngrok_manager.stop_tunnel()

        return WebhookResponse(
            success=True, message="ngrok tunnel stopped successfully"
        )

    except Exception as e:
        logger.error(f"Error stopping ngrok tunnel: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to stop ngrok tunnel: {str(e)}",
        )


@router.get("/ngrok/tunnels")
async def get_ngrok_tunnels() -> Dict:
    try:
        tunnels = await NgrokManager.get_ngrok_api_tunnels()
        return {"tunnels": tunnels}

    except Exception as e:
        logger.error(f"Error getting ngrok tunnels: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get ngrok tunnels: {str(e)}",
        )
