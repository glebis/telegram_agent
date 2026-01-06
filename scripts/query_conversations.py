#!/usr/bin/env python3
"""
Query and explore conversation data interactively.

This script provides a SQL-like interface to query conversation data
and extract specific patterns for feature development.
"""

import argparse
import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional


class ConversationQuery:
    """Interactive query tool for conversation database."""

    def __init__(self, db_path: str):
        self.db_path = Path(db_path)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row

    def close(self):
        if self.conn:
            self.conn.close()

    def search_prompts(self, keyword: str, limit: int = 20) -> List[dict]:
        """Search for prompts containing a keyword."""
        cursor = self.conn.cursor()
        results = cursor.execute("""
            SELECT
                cs.session_id,
                cs.name,
                cs.last_prompt,
                cs.created_at,
                cs.last_used,
                u.username
            FROM claude_sessions cs
            JOIN users u ON cs.user_id = u.id
            WHERE cs.last_prompt LIKE ?
            ORDER BY cs.last_used DESC
            LIMIT ?
        """, (f"%{keyword}%", limit)).fetchall()

        return [dict(row) for row in results]

    def get_sessions_by_date_range(self, start_date: str, end_date: str) -> List[dict]:
        """Get sessions within a date range."""
        cursor = self.conn.cursor()
        results = cursor.execute("""
            SELECT
                cs.session_id,
                cs.name,
                cs.last_prompt,
                cs.created_at,
                cs.last_used,
                u.username,
                JULIANDAY(cs.last_used) - JULIANDAY(cs.created_at) as duration_days
            FROM claude_sessions cs
            JOIN users u ON cs.user_id = u.id
            WHERE DATE(cs.created_at) BETWEEN ? AND ?
            ORDER BY cs.created_at DESC
        """, (start_date, end_date)).fetchall()

        return [dict(row) for row in results]

    def get_longest_sessions(self, limit: int = 10) -> List[dict]:
        """Get longest-running sessions."""
        cursor = self.conn.cursor()
        results = cursor.execute("""
            SELECT
                cs.session_id,
                cs.name,
                cs.last_prompt,
                cs.created_at,
                cs.last_used,
                JULIANDAY(cs.last_used) - JULIANDAY(cs.created_at) as duration_days,
                u.username
            FROM claude_sessions cs
            JOIN users u ON cs.user_id = u.id
            WHERE cs.last_used IS NOT NULL
            ORDER BY duration_days DESC
            LIMIT ?
        """, (limit,)).fetchall()

        return [dict(row) for row in results]

    def get_sessions_by_user(self, username: Optional[str] = None) -> List[dict]:
        """Get sessions for a specific user or all users."""
        cursor = self.conn.cursor()

        if username:
            results = cursor.execute("""
                SELECT
                    cs.session_id,
                    cs.name,
                    cs.last_prompt,
                    cs.created_at,
                    cs.last_used,
                    cs.is_active
                FROM claude_sessions cs
                JOIN users u ON cs.user_id = u.id
                WHERE u.username = ?
                ORDER BY cs.created_at DESC
            """, (username,)).fetchall()
        else:
            results = cursor.execute("""
                SELECT
                    u.username,
                    u.first_name,
                    COUNT(cs.id) as total_sessions,
                    COUNT(CASE WHEN cs.is_active THEN 1 END) as active_sessions,
                    MAX(cs.last_used) as last_activity
                FROM users u
                LEFT JOIN claude_sessions cs ON u.id = cs.user_id
                GROUP BY u.id
                ORDER BY total_sessions DESC
            """).fetchall()

        return [dict(row) for row in results]

    def export_for_training(self, output_file: str, limit: Optional[int] = None):
        """Export conversation data in format suitable for training/analysis."""
        cursor = self.conn.cursor()

        query = """
            SELECT
                cs.session_id,
                cs.last_prompt as prompt,
                cs.created_at,
                cs.last_used,
                u.username,
                JULIANDAY(cs.last_used) - JULIANDAY(cs.created_at) as duration_days
            FROM claude_sessions cs
            JOIN users u ON cs.user_id = u.id
            WHERE cs.last_prompt IS NOT NULL AND cs.last_prompt != ''
            ORDER BY cs.created_at DESC
        """

        if limit:
            query += f" LIMIT {limit}"

        results = cursor.execute(query).fetchall()
        data = [dict(row) for row in results]

        # Add metadata
        export_data = {
            "export_date": datetime.now().isoformat(),
            "total_records": len(data),
            "data": data
        }

        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w') as f:
            json.dump(export_data, f, indent=2, default=str)

        print(f"✅ Exported {len(data)} records to {output_path}")

    def analyze_prompt_patterns(self) -> dict:
        """Analyze patterns in prompts to identify feature opportunities."""
        cursor = self.conn.cursor()

        prompts = cursor.execute("""
            SELECT last_prompt
            FROM claude_sessions
            WHERE last_prompt IS NOT NULL AND last_prompt != ''
        """).fetchall()

        # Pattern analysis
        patterns = {
            "commands": [],
            "file_paths": [],
            "repeated_phrases": {},
            "questions": [],
            "technical_terms": {},
        }

        import re

        for row in prompts:
            prompt = row[0]

            # Find commands (words starting with /)
            commands = re.findall(r'/\w+', prompt)
            patterns["commands"].extend(commands)

            # Find file paths
            paths = re.findall(r'(?:/[\w\-./]+|~/[\w\-./]+)', prompt)
            patterns["file_paths"].extend(paths)

            # Find questions
            if '?' in prompt:
                sentences = prompt.split('.')
                questions = [s.strip() for s in sentences if '?' in s]
                patterns["questions"].extend(questions[:3])  # Limit per prompt

            # Find repeated words (potential domain terms)
            words = re.findall(r'\b[a-z]{4,}\b', prompt.lower())
            for word in words:
                if word not in ['that', 'this', 'with', 'from', 'have', 'will', 'when', 'what']:
                    patterns["technical_terms"][word] = patterns["technical_terms"].get(word, 0) + 1

        # Summarize
        from collections import Counter

        return {
            "top_commands": dict(Counter(patterns["commands"]).most_common(10)),
            "top_paths": dict(Counter(patterns["file_paths"]).most_common(10)),
            "common_questions": patterns["questions"][:10],
            "technical_terms": dict(sorted(patterns["technical_terms"].items(), key=lambda x: x[1], reverse=True)[:20]),
        }


def main():
    parser = argparse.ArgumentParser(description="Query conversation database")
    parser.add_argument(
        "--db",
        default="~/ai_projects/telegram_agent/data/telegram_agent.db",
        help="Path to database"
    )

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Search command
    search_parser = subparsers.add_parser("search", help="Search prompts")
    search_parser.add_argument("keyword", help="Keyword to search for")
    search_parser.add_argument("--limit", type=int, default=20, help="Max results")

    # Date range command
    date_parser = subparsers.add_parser("date-range", help="Get sessions by date range")
    date_parser.add_argument("start", help="Start date (YYYY-MM-DD)")
    date_parser.add_argument("end", help="End date (YYYY-MM-DD)")

    # Longest sessions
    longest_parser = subparsers.add_parser("longest", help="Get longest sessions")
    longest_parser.add_argument("--limit", type=int, default=10, help="Max results")

    # By user
    user_parser = subparsers.add_parser("by-user", help="Get sessions by user")
    user_parser.add_argument("--username", help="Username (optional)")

    # Export
    export_parser = subparsers.add_parser("export", help="Export data for training")
    export_parser.add_argument("output", help="Output file path")
    export_parser.add_argument("--limit", type=int, help="Max records")

    # Patterns
    patterns_parser = subparsers.add_parser("patterns", help="Analyze prompt patterns")

    args = parser.parse_args()

    db_path = Path(args.db).expanduser()
    query = ConversationQuery(str(db_path))

    try:
        if args.command == "search":
            results = query.search_prompts(args.keyword, args.limit)
            print(f"\n🔍 Found {len(results)} sessions matching '{args.keyword}':\n")
            for i, r in enumerate(results, 1):
                print(f"{i}. [{r['created_at']}] @{r['username']}")
                print(f"   Session: {r['session_id'][:8]}...")
                if r['name']:
                    print(f"   Name: {r['name']}")
                print(f"   Prompt: {r['last_prompt'][:100]}...")
                print()

        elif args.command == "date-range":
            results = query.get_sessions_by_date_range(args.start, args.end)
            print(f"\n📅 Found {len(results)} sessions between {args.start} and {args.end}:\n")
            for r in results:
                print(f"[{r['created_at']}] {r['session_id'][:8]}... ({r['duration_days']:.1f} days)")
                if r['last_prompt']:
                    print(f"  {r['last_prompt'][:80]}...")
                print()

        elif args.command == "longest":
            results = query.get_longest_sessions(args.limit)
            print(f"\n⏱️  Top {args.limit} longest sessions:\n")
            for i, r in enumerate(results, 1):
                print(f"{i}. {r['duration_days']:.1f} days - {r['session_id'][:8]}...")
                print(f"   User: @{r['username']}")
                print(f"   Created: {r['created_at']}")
                print(f"   Last used: {r['last_used']}")
                if r['last_prompt']:
                    print(f"   Prompt: {r['last_prompt'][:80]}...")
                print()

        elif args.command == "by-user":
            results = query.get_sessions_by_user(args.username)
            if args.username:
                print(f"\n👤 Sessions for @{args.username}:\n")
                for i, r in enumerate(results, 1):
                    status = "🟢" if r['is_active'] else "⚫"
                    print(f"{i}. {status} {r['session_id'][:8]}... [{r['created_at']}]")
                    if r['name']:
                        print(f"   Name: {r['name']}")
                    if r['last_prompt']:
                        print(f"   {r['last_prompt'][:80]}...")
                    print()
            else:
                print("\n👥 Sessions by user:\n")
                for r in results:
                    print(f"@{r['username']} ({r['first_name']})")
                    print(f"  Total: {r['total_sessions']}, Active: {r['active_sessions']}")
                    print(f"  Last activity: {r['last_activity']}")
                    print()

        elif args.command == "export":
            query.export_for_training(args.output, args.limit)

        elif args.command == "patterns":
            patterns = query.analyze_prompt_patterns()
            print("\n📊 PROMPT PATTERN ANALYSIS\n")

            print("Top Commands:")
            for cmd, count in patterns["top_commands"].items():
                print(f"  {cmd}: {count}")

            print("\nTop File Paths:")
            for path, count in patterns["top_paths"].items():
                print(f"  {path}: {count}")

            print("\nCommon Questions:")
            for q in patterns["common_questions"]:
                print(f"  - {q[:80]}...")

            print("\nTechnical Terms:")
            for term, count in list(patterns["technical_terms"].items())[:15]:
                print(f"  {term}: {count}")

        else:
            parser.print_help()

    finally:
        query.close()


if __name__ == "__main__":
    main()
