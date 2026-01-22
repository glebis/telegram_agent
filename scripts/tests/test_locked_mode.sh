#!/bin/bash
# Test script for auto-enable locked mode feature

set -e

DB_PATH="data/telegram_agent.db"
TEST_CHAT_ID=999999999  # Use a test chat ID that doesn't exist

echo "Testing auto-enable locked mode feature..."

# Step 1: Verify the database has the test chat
echo "1. Checking if test chat exists..."
CHAT_EXISTS=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM chats WHERE chat_id = $TEST_CHAT_ID;")

if [ "$CHAT_EXISTS" -eq 0 ]; then
  echo "   Creating test chat..."
  # Create test user first
  sqlite3 "$DB_PATH" "INSERT OR IGNORE INTO users (telegram_id, username) VALUES ($TEST_CHAT_ID, 'testuser');"
  USER_ID=$(sqlite3 "$DB_PATH" "SELECT id FROM users WHERE telegram_id = $TEST_CHAT_ID;")
  
  # Create test chat with claude_mode=0
  sqlite3 "$DB_PATH" "INSERT INTO chats (chat_id, user_id, chat_type, claude_mode) VALUES ($TEST_CHAT_ID, $USER_ID, 'private', 0);"
  echo "   ✓ Test chat created with claude_mode=0"
fi

# Step 2: Check initial claude_mode status
INITIAL_MODE=$(sqlite3 "$DB_PATH" "SELECT claude_mode FROM chats WHERE chat_id = $TEST_CHAT_ID;")
echo "2. Initial claude_mode: $INITIAL_MODE"

# Step 3: Simulate session creation by calling Python code
echo "3. Testing session save logic..."
python3 << 'PYEOF'
import asyncio
import sys
sys.path.insert(0, 'src')

from core.database import get_db_session
from services.claude_code_service import ClaudeCodeService
from models.chat import Chat
from sqlalchemy import select

async def test():
    service = ClaudeCodeService()
    test_chat_id = 999999999
    test_user_id = test_chat_id
    test_session_id = "test-session-auto-lock"
    
    # Save a new session (should trigger auto-lock)
    await service._save_session(
        chat_id=test_chat_id,
        user_id=test_user_id,
        session_id=test_session_id,
        last_prompt="Test prompt"
    )
    
    # Check if claude_mode was enabled
    async with get_db_session() as session:
        result = await session.execute(
            select(Chat).where(Chat.chat_id == test_chat_id)
        )
        chat = result.scalar_one_or_none()
        
        if chat:
            print(f"✓ claude_mode after session save: {chat.claude_mode}")
            if chat.claude_mode:
                print("✓ SUCCESS: Locked mode was auto-enabled!")
                return True
            else:
                print("✗ FAIL: Locked mode was not enabled")
                return False
        else:
            print("✗ FAIL: Chat not found")
            return False

success = asyncio.run(test())
sys.exit(0 if success else 1)
PYEOF

if [ $? -eq 0 ]; then
    echo ""
    echo "=== TEST PASSED ==="
    echo "Locked mode is auto-enabled when a new session is created"
else
    echo ""
    echo "=== TEST FAILED ==="
    exit 1
fi

# Cleanup
echo ""
echo "Cleaning up test data..."
sqlite3 "$DB_PATH" "DELETE FROM claude_sessions WHERE session_id = 'test-session-auto-lock';"
sqlite3 "$DB_PATH" "DELETE FROM chats WHERE chat_id = $TEST_CHAT_ID;"
sqlite3 "$DB_PATH" "DELETE FROM users WHERE telegram_id = $TEST_CHAT_ID;"
echo "✓ Cleanup complete"
