#!/usr/bin/env python3
"""
Telegram Bot Conversation Analysis Tool

Analyzes Claude Code sessions from the Telegram bot to identify:
- Usage patterns
- Common use cases
- Tool usage statistics
- Session characteristics
- Feature requests and improvement opportunities

This script can be run in multiple modes:
- Database analysis: Analyze session metadata from SQLite
- Log analysis: Parse app logs for conversation details
- Combined analysis: Full analysis with recommendations
"""

import argparse
import json
import logging
import re
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ConversationAnalyzer:
    """Analyzes Telegram bot conversations with Claude Code."""

    def __init__(self, db_path: str, log_path: Optional[str] = None):
        self.db_path = Path(db_path)
        self.log_path = Path(log_path) if log_path else None
        self.conn = None

    def connect_db(self):
        """Connect to SQLite database."""
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row

    def close_db(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()

    def get_session_stats(self) -> Dict:
        """Get basic session statistics from database."""
        cursor = self.conn.cursor()

        # Total sessions
        total_sessions = cursor.execute(
            "SELECT COUNT(*) FROM claude_sessions"
        ).fetchone()[0]

        # Active sessions
        active_sessions = cursor.execute(
            "SELECT COUNT(*) FROM claude_sessions WHERE is_active = 1"
        ).fetchone()[0]

        # Sessions by date
        sessions_by_date = cursor.execute("""
            SELECT DATE(created_at) as date, COUNT(*) as count
            FROM claude_sessions
            GROUP BY DATE(created_at)
            ORDER BY date DESC
            LIMIT 30
        """).fetchall()

        # Sessions with names vs unnamed
        named_sessions = cursor.execute(
            "SELECT COUNT(*) FROM claude_sessions WHERE name IS NOT NULL"
        ).fetchone()[0]

        # Average session reuse (sessions with multiple uses)
        session_reuse = cursor.execute("""
            SELECT
                AVG(JULIANDAY(last_used) - JULIANDAY(created_at)) as avg_duration_days,
                COUNT(CASE WHEN last_used != created_at THEN 1 END) as reused_count
            FROM claude_sessions
            WHERE last_used IS NOT NULL
        """).fetchone()

        # Sessions by user
        sessions_by_user = cursor.execute("""
            SELECT u.username, u.first_name, COUNT(cs.id) as session_count
            FROM claude_sessions cs
            JOIN users u ON cs.user_id = u.id
            GROUP BY cs.user_id
            ORDER BY session_count DESC
        """).fetchall()

        return {
            "total_sessions": total_sessions,
            "active_sessions": active_sessions,
            "inactive_sessions": total_sessions - active_sessions,
            "named_sessions": named_sessions,
            "unnamed_sessions": total_sessions - named_sessions,
            "avg_session_duration_days": session_reuse[0] if session_reuse[0] else 0,
            "reused_sessions": session_reuse[1] if session_reuse[1] else 0,
            "sessions_by_date": [dict(row) for row in sessions_by_date],
            "sessions_by_user": [dict(row) for row in sessions_by_user],
        }

    def get_recent_sessions(self, limit: int = 50) -> List[Dict]:
        """Get recent session details."""
        cursor = self.conn.cursor()

        sessions = cursor.execute("""
            SELECT
                cs.session_id,
                cs.name,
                cs.created_at,
                cs.last_used,
                cs.last_prompt,
                cs.is_active,
                u.username,
                u.first_name
            FROM claude_sessions cs
            JOIN users u ON cs.user_id = u.id
            ORDER BY cs.last_used DESC
            LIMIT ?
        """, (limit,)).fetchall()

        return [dict(row) for row in sessions]

    def analyze_logs(self, days: int = 7) -> Dict:
        """Analyze app logs for tool usage and patterns."""
        if not self.log_path or not self.log_path.exists():
            logger.warning("Log file not found, skipping log analysis")
            return {}

        tool_usage = Counter()
        error_patterns = Counter()
        command_patterns = Counter()
        model_usage = Counter()

        # Patterns to match
        tool_pattern = re.compile(r"tool: (\w+)")
        error_pattern = re.compile(r"ERROR.*?- (.*?)(?:\n|$)")
        command_pattern = re.compile(r"command from user.*?subcommand=(\w+)")
        model_pattern = re.compile(r"model=(\w+)")

        cutoff_date = datetime.now() - timedelta(days=days)

        try:
            with open(self.log_path, 'r') as f:
                for line in f:
                    # Parse timestamp
                    try:
                        timestamp_str = line.split(' - ')[0]
                        timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S,%f')

                        if timestamp < cutoff_date:
                            continue

                    except (ValueError, IndexError):
                        continue

                    # Count tool usage
                    if 'type=tool' in line:
                        tools = tool_pattern.findall(line)
                        tool_usage.update(tools)

                    # Track errors
                    if 'ERROR' in line:
                        errors = error_pattern.findall(line)
                        error_patterns.update(errors)

                    # Track commands
                    if 'claude_command' in line or '/claude' in line:
                        commands = command_pattern.findall(line)
                        command_patterns.update(commands)

                    # Track model usage
                    if 'model=' in line:
                        models = model_pattern.findall(line)
                        model_usage.update(models)

        except Exception as e:
            logger.error(f"Error analyzing logs: {e}")
            return {}

        return {
            "tool_usage": dict(tool_usage.most_common(20)),
            "error_patterns": dict(error_patterns.most_common(10)),
            "command_patterns": dict(command_patterns.most_common(10)),
            "model_usage": dict(model_usage.most_common()),
            "analysis_period_days": days,
        }

    def identify_use_cases(self) -> List[Dict]:
        """Identify common use cases from session prompts."""
        cursor = self.conn.cursor()

        # Get sessions with last_prompt
        sessions = cursor.execute("""
            SELECT last_prompt, created_at, name
            FROM claude_sessions
            WHERE last_prompt IS NOT NULL AND last_prompt != ''
            ORDER BY created_at DESC
            LIMIT 100
        """).fetchall()

        # Categorize prompts
        categories = {
            "file_operations": {
                "keywords": ["read", "write", "edit", "file", "create", "update"],
                "examples": []
            },
            "code_analysis": {
                "keywords": ["analyze", "review", "check", "find", "search", "bug"],
                "examples": []
            },
            "automation": {
                "keywords": ["script", "automate", "run", "execute", "command"],
                "examples": []
            },
            "note_taking": {
                "keywords": ["note", "vault", "obsidian", "daily", "journal"],
                "examples": []
            },
            "data_processing": {
                "keywords": ["process", "parse", "convert", "extract", "data"],
                "examples": []
            },
            "research": {
                "keywords": ["research", "search", "find", "investigate", "explore"],
                "examples": []
            },
            "configuration": {
                "keywords": ["config", "setup", "install", "configure", "settings"],
                "examples": []
            },
        }

        for session in sessions:
            prompt = session["last_prompt"].lower()

            for category, info in categories.items():
                if any(keyword in prompt for keyword in info["keywords"]):
                    if len(info["examples"]) < 3:
                        info["examples"].append({
                            "prompt": session["last_prompt"][:100],
                            "date": session["created_at"],
                            "name": session["name"]
                        })

        # Convert to list with counts
        use_cases = []
        for category, info in categories.items():
            if info["examples"]:
                use_cases.append({
                    "category": category,
                    "count": len(info["examples"]),
                    "examples": info["examples"]
                })

        return sorted(use_cases, key=lambda x: x["count"], reverse=True)

    def generate_recommendations(self, stats: Dict, log_analysis: Dict, use_cases: List[Dict]) -> List[str]:
        """Generate recommendations for improvements."""
        recommendations = []

        # Session naming
        if stats["unnamed_sessions"] > stats["total_sessions"] * 0.7:
            recommendations.append({
                "priority": "high",
                "category": "UX",
                "title": "Auto-suggest session names",
                "description": f"{stats['unnamed_sessions']}/{stats['total_sessions']} sessions are unnamed. "
                               "Consider auto-generating session names from the first prompt.",
                "implementation": "Use LLM to generate concise session names from initial prompts"
            })

        # Session reuse
        if stats["reused_sessions"] < stats["total_sessions"] * 0.3:
            recommendations.append({
                "priority": "medium",
                "category": "UX",
                "title": "Improve session discoverability",
                "description": f"Only {stats['reused_sessions']}/{stats['total_sessions']} sessions are reused. "
                               "Users may not be aware of session continuation feature.",
                "implementation": "Add quick access to recent sessions, better session management UI"
            })

        # Tool usage insights
        if log_analysis and "tool_usage" in log_analysis:
            top_tools = list(log_analysis["tool_usage"].keys())[:5]
            recommendations.append({
                "priority": "low",
                "category": "Feature",
                "title": "Optimize frequent tools",
                "description": f"Most used tools: {', '.join(top_tools)}. Consider shortcuts or presets.",
                "implementation": "Create tool-specific commands or quick actions"
            })

        # Use case specific
        if use_cases:
            top_use_case = use_cases[0]["category"]
            recommendations.append({
                "priority": "medium",
                "category": "Feature",
                "title": f"Optimize for {top_use_case}",
                "description": f"Most common use case is {top_use_case}. Consider dedicated features.",
                "implementation": f"Add templates, shortcuts, or specialized modes for {top_use_case}"
            })

        # Error analysis
        if log_analysis and "error_patterns" in log_analysis and log_analysis["error_patterns"]:
            top_error = list(log_analysis["error_patterns"].keys())[0]
            recommendations.append({
                "priority": "high",
                "category": "Reliability",
                "title": "Address common errors",
                "description": f"Most frequent error: {top_error[:100]}",
                "implementation": "Add better error handling and user guidance"
            })

        return recommendations

    def run_full_analysis(self, output_file: Optional[str] = None) -> Dict:
        """Run complete analysis and optionally save to file."""
        logger.info("Starting conversation analysis...")

        self.connect_db()

        try:
            # Gather all data
            logger.info("Analyzing session statistics...")
            stats = self.get_session_stats()

            logger.info("Analyzing recent sessions...")
            recent_sessions = self.get_recent_sessions(limit=20)

            logger.info("Identifying use cases...")
            use_cases = self.identify_use_cases()

            logger.info("Analyzing logs...")
            log_analysis = self.analyze_logs(days=7)

            logger.info("Generating recommendations...")
            recommendations = self.generate_recommendations(stats, log_analysis, use_cases)

            # Compile results
            results = {
                "analysis_date": datetime.now().isoformat(),
                "summary": {
                    "total_sessions": stats["total_sessions"],
                    "active_sessions": stats["active_sessions"],
                    "avg_session_duration_days": round(stats["avg_session_duration_days"], 2),
                    "session_reuse_rate": round(stats["reused_sessions"] / stats["total_sessions"] * 100, 1) if stats["total_sessions"] > 0 else 0,
                },
                "statistics": stats,
                "recent_sessions": recent_sessions,
                "use_cases": use_cases,
                "log_analysis": log_analysis,
                "recommendations": recommendations,
            }

            # Save to file if requested
            if output_file:
                output_path = Path(output_file)
                output_path.parent.mkdir(parents=True, exist_ok=True)

                with open(output_path, 'w') as f:
                    json.dump(results, f, indent=2, default=str)

                logger.info(f"Analysis saved to {output_path}")

            return results

        finally:
            self.close_db()


def print_analysis_report(results: Dict):
    """Print a formatted analysis report to console."""
    print("\n" + "="*80)
    print("TELEGRAM BOT CONVERSATION ANALYSIS REPORT")
    print("="*80)

    # Summary
    print("\n📊 SUMMARY")
    print("-" * 80)
    summary = results["summary"]
    print(f"Total Sessions: {summary['total_sessions']}")
    print(f"Active Sessions: {summary['active_sessions']}")
    print(f"Avg Session Duration: {summary['avg_session_duration_days']:.1f} days")
    print(f"Session Reuse Rate: {summary['session_reuse_rate']:.1f}%")

    # Use Cases
    if results["use_cases"]:
        print("\n🎯 TOP USE CASES")
        print("-" * 80)
        for i, use_case in enumerate(results["use_cases"][:5], 1):
            print(f"{i}. {use_case['category'].replace('_', ' ').title()}: {use_case['count']} instances")
            if use_case["examples"]:
                print(f"   Example: {use_case['examples'][0]['prompt'][:80]}...")

    # Tool Usage
    if results["log_analysis"] and "tool_usage" in results["log_analysis"]:
        print("\n🔧 TOOL USAGE (Last 7 days)")
        print("-" * 80)
        for tool, count in list(results["log_analysis"]["tool_usage"].items())[:10]:
            print(f"{tool:20s}: {count:4d}")

    # Model Usage
    if results["log_analysis"] and "model_usage" in results["log_analysis"]:
        print("\n🤖 MODEL USAGE")
        print("-" * 80)
        for model, count in results["log_analysis"]["model_usage"].items():
            print(f"{model:20s}: {count:4d}")

    # Recommendations
    print("\n💡 RECOMMENDATIONS")
    print("-" * 80)
    for i, rec in enumerate(results["recommendations"], 1):
        priority_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}
        emoji = priority_emoji.get(rec["priority"], "⚪")
        print(f"\n{i}. {emoji} {rec['title']} [{rec['category']}]")
        print(f"   {rec['description']}")
        print(f"   💭 Implementation: {rec['implementation']}")

    # Recent Activity
    if results["statistics"]["sessions_by_date"]:
        print("\n📅 RECENT ACTIVITY (Last 10 days)")
        print("-" * 80)
        for day in results["statistics"]["sessions_by_date"][:10]:
            print(f"{day['date']}: {'█' * day['count']} ({day['count']})")

    print("\n" + "="*80)


def main():
    parser = argparse.ArgumentParser(
        description="Analyze Telegram bot conversations with Claude Code"
    )
    parser.add_argument(
        "--db",
        default="~/ai_projects/telegram_agent/data/telegram_agent.db",
        help="Path to SQLite database"
    )
    parser.add_argument(
        "--log",
        default="~/ai_projects/telegram_agent/logs/app.log",
        help="Path to app log file"
    )
    parser.add_argument(
        "--output",
        "-o",
        help="Output file path (JSON format)"
    )
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="Number of days to analyze from logs"
    )
    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Don't print report to console"
    )

    args = parser.parse_args()

    # Expand paths
    db_path = Path(args.db).expanduser()
    log_path = Path(args.log).expanduser() if args.log else None

    # Create analyzer
    analyzer = ConversationAnalyzer(str(db_path), str(log_path) if log_path else None)

    # Run analysis
    results = analyzer.run_full_analysis(output_file=args.output)

    # Print report
    if not args.quiet:
        print_analysis_report(results)


if __name__ == "__main__":
    main()
