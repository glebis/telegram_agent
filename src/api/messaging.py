import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select

from ..bot.bot import get_bot
from ..core.database import get_db_session
from ..models.admin_contact import AdminContact

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/messaging", tags=["messaging"])


# Request/Response models
class SendMessageRequest(BaseModel):
    message: str
    contact_ids: Optional[List[int]] = None
    roles: Optional[List[str]] = None


class SendMessageResponse(BaseModel):
    success: bool
    sent_to: List[str]
    failed: List[str]


class AdminContactCreate(BaseModel):
    chat_id: int
    username: Optional[str] = None
    name: str
    role: Optional[str] = None
    notes: Optional[str] = None


class AdminContactResponse(BaseModel):
    id: int
    chat_id: int
    username: Optional[str]
    name: str
    role: Optional[str]
    active: bool
    notes: Optional[str]

    class Config:
        from_attributes = True


@router.post("/send", response_model=SendMessageResponse)
async def send_message(request: SendMessageRequest) -> SendMessageResponse:
    """Send a message to admin contacts."""
    logger.info(f"Send message request: {request.message[:50]}...")

    async with get_db_session() as session:
        # Build query for contacts
        query = select(AdminContact).where(AdminContact.active == True)

        if request.contact_ids:
            query = query.where(AdminContact.id.in_(request.contact_ids))

        if request.roles:
            query = query.where(AdminContact.role.in_(request.roles))

        result = await session.execute(query)
        contacts = result.scalars().all()

        if not contacts:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No matching admin contacts found",
            )

        sent_to = []
        failed = []

        bot = get_bot()
        for contact in contacts:
            try:
                success = await bot.send_message(contact.chat_id, request.message)
                if success:
                    sent_to.append(contact.name)
                    logger.info(f"Message sent to {contact.name} ({contact.chat_id})")
                else:
                    failed.append(contact.name)
                    logger.error(f"Failed to send message to {contact.name}")
            except Exception as e:
                failed.append(contact.name)
                logger.error(f"Error sending to {contact.name}: {e}")

        return SendMessageResponse(success=len(failed) == 0, sent_to=sent_to, failed=failed)


@router.get("/contacts", response_model=List[AdminContactResponse])
async def list_contacts() -> List[AdminContactResponse]:
    """List all admin contacts."""
    async with get_db_session() as session:
        result = await session.execute(select(AdminContact))
        contacts = result.scalars().all()
        return [AdminContactResponse.model_validate(c) for c in contacts]


@router.post("/contacts", response_model=AdminContactResponse, status_code=status.HTTP_201_CREATED)
async def create_contact(contact: AdminContactCreate) -> AdminContactResponse:
    """Add a new admin contact."""
    async with get_db_session() as session:
        # Check if chat_id already exists
        existing = await session.execute(
            select(AdminContact).where(AdminContact.chat_id == contact.chat_id)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Contact with chat_id {contact.chat_id} already exists",
            )

        new_contact = AdminContact(
            chat_id=contact.chat_id,
            username=contact.username,
            name=contact.name,
            role=contact.role,
            notes=contact.notes,
            active=True,
        )
        session.add(new_contact)
        await session.commit()
        await session.refresh(new_contact)

        logger.info(f"Created admin contact: {new_contact.name} ({new_contact.chat_id})")
        return AdminContactResponse.model_validate(new_contact)


@router.delete("/contacts/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_contact(contact_id: int) -> None:
    """Remove an admin contact."""
    async with get_db_session() as session:
        result = await session.execute(
            select(AdminContact).where(AdminContact.id == contact_id)
        )
        contact = result.scalar_one_or_none()

        if not contact:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Contact with id {contact_id} not found",
            )

        await session.delete(contact)
        await session.commit()
        logger.info(f"Deleted admin contact: {contact.name}")


@router.patch("/contacts/{contact_id}/toggle", response_model=AdminContactResponse)
async def toggle_contact_active(contact_id: int) -> AdminContactResponse:
    """Toggle a contact's active status."""
    async with get_db_session() as session:
        result = await session.execute(
            select(AdminContact).where(AdminContact.id == contact_id)
        )
        contact = result.scalar_one_or_none()

        if not contact:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Contact with id {contact_id} not found",
            )

        contact.active = not contact.active
        await session.commit()
        await session.refresh(contact)

        logger.info(f"Toggled contact {contact.name} active={contact.active}")
        return AdminContactResponse.model_validate(contact)
