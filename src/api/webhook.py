import logging
from typing import Dict, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from pydantic import BaseModel, HttpUrl

from ..utils.ngrok_utils import NgrokManager, WebhookManager, auto_update_webhook_on_restart

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/webhook", tags=["webhook"])


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
    bot_token: str,  # This should come from dependency injection in main app
) -> WebhookResponse:
    try:
        webhook_manager = WebhookManager(bot_token)
        
        success, message = await webhook_manager.set_webhook(
            str(request.url), request.secret_token
        )
        
        if success:
            logger.info(f"Webhook updated via API: {request.url}")
            return WebhookResponse(
                success=True,
                message=message,
                webhook_url=str(request.url)
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to update webhook: {message}"
            )
            
    except Exception as e:
        logger.error(f"Error updating webhook: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal error updating webhook: {str(e)}"
        )


@router.post("/refresh", response_model=WebhookResponse)
async def refresh_webhook(
    request: WebhookRefreshRequest,
    background_tasks: BackgroundTasks,
    bot_token: str,  # This should come from dependency injection in main app
) -> WebhookResponse:
    try:
        success, message, webhook_url = await auto_update_webhook_on_restart(
            bot_token=bot_token,
            port=request.port,
            webhook_path=request.webhook_path,
            secret_token=request.secret_token,
        )
        
        if success:
            return WebhookResponse(
                success=True,
                message=message,
                webhook_url=webhook_url
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=message
            )
            
    except Exception as e:
        logger.error(f"Error refreshing webhook: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal error refreshing webhook: {str(e)}"
        )


@router.get("/status", response_model=WebhookStatusResponse)
async def get_webhook_status(
    bot_token: str,  # This should come from dependency injection in main app
) -> WebhookStatusResponse:
    try:
        webhook_manager = WebhookManager(bot_token)
        
        # Get Telegram webhook info
        telegram_webhook = await webhook_manager.get_webhook_info()
        
        # Get ngrok tunnel status
        ngrok_manager = NgrokManager()
        ngrok_status = ngrok_manager.get_tunnel_status()
        
        # Determine if webhook is active
        active = (
            telegram_webhook.get("url", "") != "" and
            ngrok_status.get("active", False)
        )
        
        return WebhookStatusResponse(
            telegram_webhook=telegram_webhook,
            ngrok_status=ngrok_status,
            active=active
        )
        
    except Exception as e:
        logger.error(f"Error getting webhook status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal error getting webhook status: {str(e)}"
        )


@router.delete("/", response_model=WebhookResponse)
async def delete_webhook(
    bot_token: str,  # This should come from dependency injection in main app
) -> WebhookResponse:
    try:
        webhook_manager = WebhookManager(bot_token)
        
        success, message = await webhook_manager.delete_webhook()
        
        if success:
            return WebhookResponse(
                success=True,
                message=message
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=message
            )
            
    except Exception as e:
        logger.error(f"Error deleting webhook: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal error deleting webhook: {str(e)}"
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
            webhook_url=public_url
        )
        
    except Exception as e:
        logger.error(f"Error starting ngrok tunnel: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start ngrok tunnel: {str(e)}"
        )


@router.post("/ngrok/stop", response_model=WebhookResponse)
async def stop_ngrok_tunnel() -> WebhookResponse:
    try:
        ngrok_manager = NgrokManager()
        ngrok_manager.stop_tunnel()
        
        return WebhookResponse(
            success=True,
            message="ngrok tunnel stopped successfully"
        )
        
    except Exception as e:
        logger.error(f"Error stopping ngrok tunnel: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to stop ngrok tunnel: {str(e)}"
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
            detail=f"Failed to get ngrok tunnels: {str(e)}"
        )