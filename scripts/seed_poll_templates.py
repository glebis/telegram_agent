#!/usr/bin/env python3
"""
Seed database with diverse poll templates.

This script creates a comprehensive library of poll templates covering:
- Emotions and mood tracking
- Decision making and priorities
- Activity and productivity
- Energy levels and focus
- Blockers and challenges
- Reflections and insights
- Satisfaction and progress
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.database import get_db_session, init_database
from src.models.poll_response import PollTemplate

# Poll template library
TEMPLATES = [
    # ===== EMOTION TRACKING =====
    {
        "poll_category": "emotion",
        "question": "How are you feeling right now?",
        "options": ["😊 Great", "🙂 Good", "😐 Okay", "😕 Not great", "😞 Struggling"],
        "poll_type": "emotion",
        "schedule_times": ["09:00", "14:00", "18:00", "21:00"],
        "priority": 9
    },
    {
        "poll_category": "emotion",
        "question": "What's your current mood?",
        "options": ["🔥 Energized", "😌 Calm", "🤔 Thoughtful", "😴 Tired", "😤 Stressed"],
        "poll_type": "emotion",
        "schedule_times": ["10:00", "15:00", "19:00"],
        "priority": 8
    },
    {
        "poll_category": "emotion",
        "question": "How satisfied do you feel with today so far?",
        "options": ["💯 Very satisfied", "👍 Satisfied", "😐 Neutral", "👎 Dissatisfied", "😞 Very dissatisfied"],
        "poll_type": "emotion",
        "schedule_times": ["17:00", "20:00"],
        "priority": 7
    },

    # ===== ENERGY & FOCUS =====
    {
        "poll_category": "energy",
        "question": "What's your energy level?",
        "options": ["⚡ High energy", "🔋 Good energy", "🪫 Low energy", "😴 Very tired"],
        "poll_type": "energy",
        "schedule_times": ["08:00", "12:00", "16:00", "20:00"],
        "priority": 9
    },
    {
        "poll_category": "energy",
        "question": "How's your focus right now?",
        "options": ["🎯 Deep focus", "✅ Focused", "🤷 Scattered", "💤 Can't focus"],
        "poll_type": "focus",
        "schedule_times": ["09:00", "13:00", "15:00"],
        "priority": 8
    },
    {
        "poll_category": "energy",
        "question": "Are you in a flow state?",
        "options": ["🌊 Yes, deep flow!", "✨ Getting there", "🤔 Trying to focus", "❌ Not at all"],
        "poll_type": "focus",
        "schedule_times": ["10:00", "14:00", "16:00"],
        "priority": 7
    },

    # ===== ACTIVITY TRACKING =====
    {
        "poll_category": "activity",
        "question": "What are you working on right now?",
        "options": ["💻 Deep work", "📧 Communications", "📖 Learning", "🎨 Creating", "🏃 Taking a break"],
        "poll_type": "activity",
        "schedule_times": ["10:00", "13:00", "15:00", "17:00"],
        "priority": 8
    },
    {
        "poll_category": "activity",
        "question": "What's your main focus area today?",
        "options": ["🎯 Priority project", "📋 Admin tasks", "💡 Exploration", "🔧 Problem solving", "📚 Learning"],
        "poll_type": "activity",
        "schedule_times": ["09:00", "14:00"],
        "priority": 7
    },
    {
        "poll_category": "activity",
        "question": "Are you in creation mode or consumption mode?",
        "options": ["🎨 Creating", "📖 Learning/Reading", "🤔 Planning", "💬 Collaborating", "😴 Resting"],
        "poll_type": "activity",
        "schedule_times": ["11:00", "15:00", "19:00"],
        "priority": 6
    },

    # ===== DECISION & PRIORITY =====
    {
        "poll_category": "decision",
        "question": "What should you prioritize next?",
        "options": ["🎯 Most important task", "🔥 Urgent items", "💡 Creative work", "📧 Communications", "🛑 Take a break"],
        "poll_type": "decision",
        "schedule_times": ["09:00", "13:00", "16:00"],
        "priority": 8
    },
    {
        "poll_category": "decision",
        "question": "Should you keep working or switch tasks?",
        "options": ["⏩ Keep going", "🔄 Switch tasks", "🛑 Take a break", "📝 Reflect first"],
        "poll_type": "decision",
        "schedule_times": ["11:00", "14:00", "17:00"],
        "priority": 7
    },

    # ===== BLOCKERS & CHALLENGES =====
    {
        "poll_category": "blocker",
        "question": "What's blocking you right now?",
        "options": ["✅ Nothing!", "😴 Low energy", "🤔 Unclear goal", "🔧 Technical issue", "💬 Waiting on others"],
        "poll_type": "blocker",
        "schedule_times": ["11:00", "15:00", "18:00"],
        "priority": 7
    },
    {
        "poll_category": "blocker",
        "question": "Do you feel stuck?",
        "options": ["✨ Flowing smoothly", "🤷 A bit stuck", "🛑 Very stuck", "❓ Not sure"],
        "poll_type": "blocker",
        "schedule_times": ["12:00", "16:00"],
        "priority": 6
    },

    # ===== REFLECTION & INSIGHTS =====
    {
        "poll_category": "reflection",
        "question": "What went well today?",
        "options": ["🎯 Achieved goals", "💡 Had insights", "🤝 Good collaboration", "📚 Learned something", "😌 Felt balanced"],
        "poll_type": "reflection",
        "schedule_times": ["18:00", "20:00", "22:00"],
        "priority": 8
    },
    {
        "poll_category": "reflection",
        "question": "What could have gone better?",
        "options": ["⏰ Time management", "🎯 Focus/clarity", "⚡ Energy levels", "🤝 Communication", "✅ Nothing major!"],
        "poll_type": "reflection",
        "schedule_times": ["19:00", "21:00"],
        "priority": 7
    },
    {
        "poll_category": "reflection",
        "question": "Did you learn something new today?",
        "options": ["💡 Yes, big insight!", "✅ Yes, small thing", "🤔 Maybe", "❌ Not really"],
        "poll_type": "reflection",
        "schedule_times": ["20:00"],
        "priority": 6
    },

    # ===== PROGRESS & SATISFACTION =====
    {
        "poll_category": "progress",
        "question": "How much progress did you make today?",
        "options": ["🚀 Major progress", "✅ Good progress", "🤷 Some progress", "😕 Little progress", "❌ None"],
        "poll_type": "progress",
        "schedule_times": ["17:00", "21:00"],
        "priority": 8
    },
    {
        "poll_category": "progress",
        "question": "Are you working on what matters most?",
        "options": ["🎯 Yes, totally aligned", "✅ Mostly yes", "🤷 Not sure", "❌ No, distracted"],
        "poll_type": "satisfaction",
        "schedule_times": ["11:00", "15:00"],
        "priority": 7
    },
    {
        "poll_category": "progress",
        "question": "How satisfied are you with your work quality today?",
        "options": ["⭐ Excellent", "✅ Good", "😐 Okay", "😕 Could be better"],
        "poll_type": "satisfaction",
        "schedule_times": ["18:00"],
        "priority": 6
    },

    # ===== CREATIVE & EXPLORATION =====
    {
        "poll_category": "creative",
        "question": "Are you in exploration mode or execution mode?",
        "options": ["🔬 Exploring", "🎨 Creating", "⚙️ Executing", "🤔 Planning", "😴 Resting"],
        "poll_type": "activity",
        "schedule_times": ["10:00", "14:00", "16:00"],
        "priority": 6
    },
    {
        "poll_category": "creative",
        "question": "What's inspiring you right now?",
        "options": ["💡 New ideas", "📚 Learning", "🤝 Collaboration", "🎨 Creative work", "😌 Nothing specific"],
        "poll_type": "emotion",
        "schedule_times": ["11:00", "15:00"],
        "priority": 5
    },

    # ===== HEALTH & WELL-BEING =====
    {
        "poll_category": "health",
        "question": "How are you treating your body?",
        "options": ["💪 Great (exercise, food, rest)", "✅ Good", "😐 Okay", "😕 Could be better"],
        "poll_type": "satisfaction",
        "schedule_times": ["12:00", "19:00"],
        "priority": 6
    },
    {
        "poll_category": "health",
        "question": "When did you last take a break?",
        "options": ["✅ Recently", "🤷 A while ago", "😓 Too long ago", "🛑 Taking one now!"],
        "poll_type": "activity",
        "schedule_times": ["11:00", "14:00", "17:00"],
        "priority": 5
    },

    # ===== LEARNING & GROWTH =====
    {
        "poll_category": "learning",
        "question": "What are you curious about right now?",
        "options": ["🔬 Technical topic", "🎨 Creative skill", "💼 Business/strategy", "🧠 Personal growth", "❌ Nothing specific"],
        "poll_type": "activity",
        "schedule_times": ["10:00", "16:00"],
        "priority": 5
    },
    {
        "poll_category": "learning",
        "question": "Did you ask good questions today?",
        "options": ["❓ Yes, great questions!", "✅ Some questions", "🤷 Not really", "❌ No"],
        "poll_type": "reflection",
        "schedule_times": ["18:00", "21:00"],
        "priority": 5
    },
]


async def seed_templates():
    """Seed database with poll templates."""
    print("🌱 Seeding poll templates...")

    # Initialize database
    await init_database()

    async with get_db_session() as session:
        # Check if templates already exist
        from sqlalchemy import select, func, delete, text
        result = await session.execute(select(func.count(PollTemplate.id)))
        existing_count = result.scalar()

        if existing_count > 0:
            print(f"⚠️  Found {existing_count} existing templates. Clear them? (y/n)")
            response = input().strip().lower()
            if response == 'y':
                await session.execute(delete(PollTemplate))
                await session.commit()
                print("✅ Cleared existing templates")
            else:
                print("❌ Aborted. Run with --force to overwrite.")
                return

        # Insert templates
        for template_data in TEMPLATES:
            template = PollTemplate(**template_data)
            session.add(template)

        await session.commit()
        print(f"✅ Seeded {len(TEMPLATES)} poll templates")

        # Print summary by category
        result = await session.execute(
            text("""
            SELECT poll_type, COUNT(*) as count
            FROM poll_templates
            GROUP BY poll_type
            ORDER BY count DESC
            """)
        )
        rows = result.fetchall()

        print("\n📊 Template distribution:")
        for row in rows:
            poll_type, count = row
            print(f"  {poll_type}: {count}")


if __name__ == "__main__":
    asyncio.run(seed_templates())
