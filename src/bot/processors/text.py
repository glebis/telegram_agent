"""
Text processor mixin — text, command, contact, poll, and sync helper methods.

Methods:
- _process_text: Route text messages to Claude or default handler
- _process_command: Route /claude, /meta, /dev commands
- _process_claude_command: Legacy /claude command handler
- _process_contacts: Route contact messages
- _process_with_polls: Format and route poll messages
- _mark_as_read_sync: React to messages with emoji (sync)
- _send_typing_sync: Send typing indicator (sync)
- _send_message_sync: Send message via Telegram API (sync)

Extracted from combined_processor.py as part of #152.
"""

import logging
import os
from typing import TYPE_CHECKING, Any, Optional

from ...core.error_messages import sanitize_error
from ...services.message_buffer import CombinedMessage
from ...services.reply_context import MessageType, ReplyContext
from ...utils.task_tracker import create_tracked_task

logger = logging.getLogger(__name__)


class TextProcessorMixin:
    """Mixin for text/command processing and sync Telegram helpers."""

    if TYPE_CHECKING:
        # Provided by CombinedMessageProcessor.__init__
        reply_service: Any

    def _mark_as_read_sync(
        self,
        chat_id: int,
        message_ids: list,
        emoji: str = "👀",
    ) -> None:
        """Mark messages as read by reacting with an emoji (sync subprocess version).

        Note: Telegram only allows specific emojis for reactions. Valid ones include:
        👍, 👎, ❤️, 🔥, 👏, 😁, 🤔, 👀, 🎉, 🤩, 😎, 🙏, etc.
        NOT valid: ✅, ✔️, and many other common emojis
        """
        import requests

        bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        if not bot_token:
            return

        for msg_id in message_ids:
            try:
                # Use requests in sync mode to avoid async blocking
                url = f"https://api.telegram.org/bot{bot_token}/setMessageReaction"
                payload = {
                    "chat_id": chat_id,
                    "message_id": msg_id,
                    "reaction": [{"type": "emoji", "emoji": emoji}],
                }
                response = requests.post(url, json=payload, timeout=5)
                result = response.json()
                if result.get("ok"):
                    logger.info(f"Marked message {msg_id} with {emoji}")
                else:
                    logger.warning(
                        f"Failed to react to {msg_id}: {result.get('description', 'Unknown error')}"
                    )
            except Exception as e:
                logger.debug(f"Could not react to message {msg_id}: {e}")

    def _send_typing_sync(self, chat_id: int) -> None:
        """Send typing indicator (sync version to avoid async blocking)."""
        import requests

        bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        if not bot_token:
            return

        try:
            url = f"https://api.telegram.org/bot{bot_token}/sendChatAction"
            payload = {"chat_id": chat_id, "action": "typing"}
            requests.post(url, json=payload, timeout=5)
            logger.debug(f"Sent typing indicator to {chat_id}")
        except Exception as e:
            logger.debug(f"Could not send typing indicator: {e}")

    def _send_message_sync(
        self,
        chat_id: int,
        text: str,
        parse_mode: str = "HTML",
        reply_to_message_id: int = None,
    ) -> bool:
        """Send a message using sync requests to avoid async blocking."""
        import requests

        bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        if not bot_token:
            return False

        try:
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            payload = {
                "chat_id": chat_id,
                "text": text,
                "parse_mode": parse_mode,
            }
            if reply_to_message_id:
                payload["reply_to_message_id"] = reply_to_message_id

            response = requests.post(url, json=payload, timeout=10)
            result = response.json()
            if result.get("ok"):
                logger.info(f"Sent message to {chat_id}: {text[:50]}...")
                return True
            else:
                logger.error(f"Failed to send message: {result}")
                return False
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            return False

    async def _process_command(self, combined: CombinedMessage) -> None:
        """
        Process a combined message that contains a /claude, /meta, or /dev command.

        Routes to appropriate handler based on command type:
        - /claude: default behavior (current working directory)
        - /meta: execute in telegram_agent directory
        - /dev: execute in current working directory
        """
        from ..handlers import execute_claude_prompt

        # Get the command message
        cmd_msg = combined.get_command_message()
        if not cmd_msg:
            logger.error("No command found in combined message")
            return

        update = cmd_msg.update
        context = cmd_msg.context
        command_type = cmd_msg.command_type

        # Determine custom_cwd based on command type
        custom_cwd = None
        if command_type == "meta":
            from ...core.config import PROJECT_ROOT

            custom_cwd = str(PROJECT_ROOT)
            logger.info(f"Using custom_cwd for /meta: {custom_cwd}")
        # /dev and /claude use default (None)

        # The combined_text already includes the command prompt + any follow-up text
        full_prompt = combined.combined_text

        # Prepend forward context if present
        forward_context = combined.get_forward_context()
        if forward_context:
            full_prompt = f"{forward_context}\n\n{full_prompt}"
            logger.info(f"Added forward context to prompt: {forward_context}")

        logger.info(
            f"Processing /{command_type} command with combined prompt: "
            f"chat={combined.chat_id}, prompt_len={len(full_prompt)}, "
            f"messages_combined={len(combined.messages)}"
        )

        # Run command execution in a background task to avoid blocking
        async def run_command():
            try:
                if combined.has_images():
                    # Download and include images in the prompt
                    await self._send_images_to_claude(
                        combined, full_prompt, custom_cwd=custom_cwd
                    )
                elif combined.has_voice():
                    # Transcribe voice and add to prompt
                    await self._process_with_voice(combined, None, is_claude_mode=True)
                elif combined.has_documents():
                    # Include documents
                    await self._process_documents(combined, None, is_claude_mode=True)
                else:
                    # Text-only prompt - detect URLs for logging
                    from ..message_handlers import extract_urls

                    urls = extract_urls(full_prompt)
                    if urls:
                        logger.info(
                            f"Detected {len(urls)} URL(s) in prompt: {urls[:3]}"
                        )  # Log first 3
                    logger.info(
                        f"Calling execute_claude_prompt with {len(full_prompt)} chars"
                    )
                    await execute_claude_prompt(
                        update, context, full_prompt, custom_cwd=custom_cwd
                    )
                    logger.info("execute_claude_prompt completed")
            except Exception as e:
                logger.error(f"Error in _process_command: {e}", exc_info=True)
                try:
                    await context.bot.send_message(
                        chat_id=combined.chat_id,
                        text=sanitize_error(
                            e, context=f"processing /{command_type} command"
                        ),
                    )
                except Exception:
                    pass

        # Schedule the task to run in the background
        create_tracked_task(run_command(), name=f"{command_type}_command")

    async def _process_claude_command(self, combined: CombinedMessage) -> None:
        """
        Process a combined message that contains a /claude command.

        The /claude command prompt is combined with any follow-up text messages
        that arrived within the buffer timeout window.
        """
        from ..handlers import execute_claude_prompt

        # Get the /claude command message for update/context
        claude_msg = combined.get_claude_command_message()
        if not claude_msg:
            logger.error("No /claude command found in combined message")
            return

        update = claude_msg.update
        context = claude_msg.context

        # The combined_text already includes the /claude prompt + any follow-up text
        full_prompt = combined.combined_text

        # Prepend forward context if present
        forward_context = combined.get_forward_context()
        if forward_context:
            full_prompt = f"{forward_context}\n\n{full_prompt}"
            logger.info(f"Added forward context to prompt: {forward_context}")

        logger.info(
            f"Processing /claude command with combined prompt: "
            f"chat={combined.chat_id}, prompt_len={len(full_prompt)}, "
            f"messages_combined={len(combined.messages)}"
        )

        # Check for images that should be included
        # Run Claude execution in a background task to avoid blocking

        async def run_claude():
            try:
                if combined.has_images():
                    # Download and include images in the prompt
                    await self._send_images_to_claude(combined, full_prompt)
                elif combined.has_voice():
                    # Transcribe voice and add to prompt
                    await self._process_with_voice(combined, None, is_claude_mode=True)
                elif combined.has_documents():
                    # Include documents
                    await self._process_documents(combined, None, is_claude_mode=True)
                else:
                    # Text-only prompt - detect URLs for logging
                    from ..message_handlers import extract_urls

                    urls = extract_urls(full_prompt)
                    if urls:
                        logger.info(
                            f"Detected {len(urls)} URL(s) in prompt: {urls[:3]}"
                        )  # Log first 3
                    logger.info(
                        f"Calling execute_claude_prompt with {len(full_prompt)} chars"
                    )
                    await execute_claude_prompt(update, context, full_prompt)
                    logger.info("execute_claude_prompt completed")
            except Exception as e:
                logger.error(f"Error in _process_claude_command: {e}", exc_info=True)
                try:
                    await context.bot.send_message(
                        chat_id=combined.chat_id,
                        text=sanitize_error(e, context="processing Claude command"),
                    )
                except Exception:
                    pass

        # Schedule the task to run in the background
        create_tracked_task(run_claude(), name="claude_command")

    async def _process_text(
        self,
        combined: CombinedMessage,
        reply_context: Optional[ReplyContext],
        is_claude_mode: bool,
    ) -> None:
        """Process text-only message."""
        from ..handlers import execute_claude_prompt
        from ..message_handlers import (
            extract_urls,
            handle_link_message,
            handle_text_message,
        )

        update = combined.primary_update
        context = combined.primary_context
        message = combined.primary_message

        text = combined.combined_text

        # Check if this is a reply to a trail review completion
        is_trail_reply = False
        trail_prompt = None
        if (
            reply_context
            and hasattr(reply_context, "trail_path")
            and reply_context.trail_path
        ):
            is_trail_reply = True
            from ...services.trail_review_service import get_trail_review_service

            trail_service = get_trail_review_service()
            trail_prompt = trail_service.build_trail_context_for_claude(
                trail_path=reply_context.trail_path,
                trail_name=getattr(reply_context, "trail_name", "Unknown"),
                answers=getattr(reply_context, "trail_answers", {}),
                user_comment=text,
            )
            logger.info(
                f"Trail review reply detected: trail={reply_context.trail_name}, "
                f"comment_len={len(text)}"
            )

        # Build full prompt with reply context
        # Track if we're replying to a Claude message (should continue that session)
        is_claude_reply = False

        if trail_prompt:
            full_prompt = trail_prompt
        elif reply_context:
            full_prompt = self.reply_service.build_reply_prompt(
                reply_context,
                text,
                include_original=True,
            )

            # If replying to Claude response, use that session
            if reply_context.message_type == MessageType.CLAUDE_RESPONSE:
                is_claude_reply = True
                # Force use of the same session
                if reply_context.session_id and context.user_data is not None:
                    context.user_data["force_session_id"] = reply_context.session_id
                    logger.info(
                        f"Replying to Claude message, forcing session: {reply_context.session_id}"
                    )

        else:
            full_prompt = text

        # Check for link + comment pair (takes precedence over forward_context)
        link_comment_ctx = combined.get_link_comment_context()
        if link_comment_ctx:
            full_prompt = link_comment_ctx
            logger.info("Using link + comment semantic formatting for prompt")

        # Check for URLs - but only capture to inbox if NOT in Claude mode
        # and NOT replying to a Claude message or trail review
        urls = extract_urls(text)

        if urls and not is_claude_mode and not is_claude_reply and not is_trail_reply:
            # Handle as link capture to Obsidian inbox
            await handle_link_message(message, urls)
            return

        # Prepend forward context if present
        forward_context = combined.get_forward_context()
        if forward_context:
            full_prompt = f"{forward_context}\n\n{full_prompt}"
            logger.info(f"Added forward context to text prompt: {forward_context}")

        # Route to Claude if: Claude mode is active OR replying to a Claude message
        # OR replying to a trail review (always goes to Claude)
        if is_claude_mode or is_claude_reply or is_trail_reply:
            # Run Claude execution in a background task to avoid blocking webhook
            pass

            async def run_claude():
                try:
                    await execute_claude_prompt(update, context, full_prompt)
                except Exception as e:
                    logger.error(
                        f"Error in _process_text Claude execution: {e}", exc_info=True
                    )
                    try:
                        await context.bot.send_message(
                            chat_id=combined.chat_id,
                            text=sanitize_error(e, context="processing message"),
                        )
                    except Exception:
                        pass

            create_tracked_task(run_claude(), name="claude_text")
        else:
            # Use existing text handler
            await handle_text_message(update, context)

    async def _process_contacts(self, combined: CombinedMessage) -> None:
        """Process contact messages."""
        from ..message_handlers import handle_contact_message

        # Process first contact
        if combined.contacts:
            first_contact = combined.contacts[0]
            await handle_contact_message(
                first_contact.update,
                first_contact.context,
            )

    async def _process_with_polls(
        self,
        combined: CombinedMessage,
        reply_context: Optional[ReplyContext],
        is_claude_mode: bool,
    ) -> None:
        """Process poll messages - format poll content and route to Claude or display."""
        from ..handlers import execute_claude_prompt

        logger.info(
            f"_process_with_polls: claude_mode={is_claude_mode}, "
            f"polls={len(combined.polls)}, text_len={len(combined.combined_text)}"
        )

        update = combined.primary_update
        context = combined.primary_context
        combined.primary_message

        # Build a text representation of each poll
        poll_descriptions = []
        for poll_msg in combined.polls:
            desc_parts = []
            question = poll_msg.poll_question or "Unknown question"
            options = poll_msg.poll_options or []
            poll_type = poll_msg.poll_type or "regular"
            voter_count = poll_msg.poll_total_voter_count or 0

            desc_parts.append(f'📊 Poll: "{question}"')
            desc_parts.append(f"   Type: {poll_type}")
            if voter_count > 0:
                desc_parts.append(f"   Total votes: {voter_count}")

            # Format options with numbering
            for i, opt in enumerate(options, 1):
                desc_parts.append(f"   {i}. {opt}")

            # Check if this poll has been voted on (from Telegram's Poll object)
            # The message.poll object may contain the user's chosen option
            if poll_msg.message and poll_msg.message.poll:
                poll_obj = poll_msg.message.poll
                # Check each option for voter count or is_chosen
                voted_options = []
                for poll_opt in poll_obj.options:
                    if getattr(poll_opt, "voter_count", 0) > 0:
                        voted_options.append(
                            f"{poll_opt.text} ({poll_opt.voter_count} votes)"
                        )

                if voted_options:
                    desc_parts.append(f"   Votes: {', '.join(voted_options)}")

            poll_descriptions.append("\n".join(desc_parts))

        poll_text = "\n\n".join(poll_descriptions)

        # Build full prompt
        prompt_parts = []

        # Add reply context if present
        if reply_context:
            prompt_parts.append(
                self.reply_service.build_reply_prompt(
                    reply_context,
                    combined.combined_text or "",
                    include_original=True,
                )
            )

        # Add poll content
        prompt_parts.append(poll_text)

        # Add any accompanying text
        if combined.combined_text:
            prompt_parts.append(combined.combined_text)

        full_prompt = "\n\n".join(prompt_parts)

        # Prepend forward context if present
        forward_context = combined.get_forward_context()
        if forward_context:
            full_prompt = f"{forward_context}\n\n{full_prompt}"
            logger.info(f"Added forward context to poll prompt: {forward_context}")

        # Route to Claude if:
        # 1. Claude mode is active, OR
        # 2. Replying to a Claude Code session message
        should_route_to_claude = is_claude_mode or (
            reply_context and reply_context.session_id
        )

        if should_route_to_claude:
            # Run Claude execution in a background task
            async def run_claude():
                try:
                    await execute_claude_prompt(update, context, full_prompt)
                except Exception as e:
                    logger.error(f"Error in poll Claude execution: {e}", exc_info=True)
                    try:
                        await context.bot.send_message(
                            chat_id=combined.chat_id,
                            text=sanitize_error(e, context="processing poll"),
                        )
                    except Exception:
                        pass

            create_tracked_task(run_claude(), name="claude_poll_analysis")
        else:
            # Non-Claude mode: display the poll content as formatted text
            display_parts = ["<b>📊 Poll received:</b>\n"]
            for poll_msg in combined.polls:
                question = poll_msg.poll_question or "Unknown"
                options = poll_msg.poll_options or []
                display_parts.append(f"<b>{question}</b>")
                for i, opt in enumerate(options, 1):
                    display_parts.append(f"  {i}. {opt}")

                if poll_msg.message and poll_msg.message.poll:
                    poll_obj = poll_msg.message.poll
                    for poll_opt in poll_obj.options:
                        if getattr(poll_opt, "voter_count", 0) > 0:
                            display_parts.append(
                                f"  📌 {poll_opt.text}: {poll_opt.voter_count} vote(s)"
                            )

            display_text = "\n".join(display_parts)

            self._send_message_sync(
                combined.chat_id,
                display_text,
                parse_mode="HTML",
            )
