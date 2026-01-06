#!/usr/bin/env python3
"""
AI-Powered Feature Suggestion Tool

Analyzes conversation patterns and suggests new features or improvements
for the Telegram bot. This script can be automated to run periodically
and create GitHub issues or feature requests automatically.
"""

import argparse
import json
import sqlite3
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List


class FeatureSuggester:
    """Suggests features based on conversation analysis."""

    def __init__(self, db_path: str, analysis_path: str = None):
        self.db_path = Path(db_path)
        self.analysis_path = Path(analysis_path) if analysis_path else None
        self.conn = None
        self.analysis_data = None

    def load_analysis(self):
        """Load existing analysis if available."""
        if self.analysis_path and self.analysis_path.exists():
            with open(self.analysis_path, 'r') as f:
                self.analysis_data = json.load(f)

    def connect_db(self):
        """Connect to database."""
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row

    def close_db(self):
        """Close database."""
        if self.conn:
            self.conn.close()

    def analyze_repeated_patterns(self) -> List[Dict]:
        """Find repeated prompts that could be automated."""
        cursor = self.conn.cursor()

        # Get all prompts
        prompts = cursor.execute("""
            SELECT last_prompt
            FROM claude_sessions
            WHERE last_prompt IS NOT NULL AND last_prompt != ''
        """).fetchall()

        # Simple pattern matching
        prompt_texts = [p[0] for p in prompts]

        # Find similar prompts (could be enhanced with ML)
        pattern_counts = Counter()
        for prompt in prompt_texts:
            # Normalize: lowercase, remove URLs, truncate
            normalized = prompt.lower()
            # Extract first 50 chars as pattern
            pattern = normalized[:50]
            pattern_counts[pattern] += 1

        # Identify frequently repeated patterns
        repeated = [
            {
                "pattern": pattern,
                "count": count,
                "suggestion": self._suggest_for_pattern(pattern)
            }
            for pattern, count in pattern_counts.most_common(10)
            if count > 2  # Only patterns that repeat 3+ times
        ]

        return repeated

    def _suggest_for_pattern(self, pattern: str) -> Dict:
        """Suggest a feature for a repeated pattern."""
        pattern = pattern.lower()

        suggestions = {
            "youtube": {
                "feature": "YouTube Processor Shortcut",
                "description": "Add /yt command to quickly process YouTube videos",
                "priority": "high",
                "implementation": "Create dedicated handler for YouTube URLs with transcript extraction"
            },
            "create note": {
                "feature": "Quick Note Creation",
                "description": "Add /note command to create notes with auto-linking",
                "priority": "medium",
                "implementation": "Template-based note creation with semantic search for links"
            },
            "analyze": {
                "feature": "Analysis Templates",
                "description": "Pre-defined analysis workflows (code, text, data)",
                "priority": "medium",
                "implementation": "Create analysis presets with customizable prompts"
            },
            "research": {
                "feature": "Research Mode",
                "description": "Dedicated research workflow with source tracking",
                "priority": "high",
                "implementation": "Multi-step research process with bibliography management"
            },
            "test": {
                "feature": "Test Runner Integration",
                "description": "Quick test execution and result formatting",
                "priority": "low",
                "implementation": "Integrate with pytest/jest, format results nicely"
            },
            "voice": {
                "feature": "Voice Command Shortcuts",
                "description": "Recognize common voice commands and auto-execute",
                "priority": "medium",
                "implementation": "Pattern matching on transcripts with command dispatch"
            },
        }

        for keyword, suggestion in suggestions.items():
            if keyword in pattern:
                return suggestion

        return {
            "feature": "Custom Workflow",
            "description": f"Create workflow for pattern: {pattern[:30]}...",
            "priority": "low",
            "implementation": "Analyze specific use case"
        }

    def suggest_tool_shortcuts(self) -> List[Dict]:
        """Suggest shortcuts for frequently used tools."""
        if not self.analysis_data or "log_analysis" not in self.analysis_data:
            return []

        tool_usage = self.analysis_data["log_analysis"].get("tool_usage", {})
        suggestions = []

        # High-usage tools that could benefit from shortcuts
        for tool, count in sorted(tool_usage.items(), key=lambda x: x[1], reverse=True)[:5]:
            if count < 10:  # Skip if not frequent enough
                continue

            suggestion = {
                "tool": tool,
                "usage_count": count,
                "suggestions": []
            }

            if tool == "Read":
                suggestion["suggestions"].append({
                    "feature": "Recent Files Quick Access",
                    "description": "Show recently read files for quick re-opening",
                    "priority": "medium"
                })

            elif tool == "Write":
                suggestion["suggestions"].append({
                    "feature": "Write Templates",
                    "description": "Pre-defined templates for common file types",
                    "priority": "low"
                })

            elif tool == "Bash":
                suggestion["suggestions"].append({
                    "feature": "Command History",
                    "description": "Quick access to recently run commands",
                    "priority": "medium"
                })

            elif tool == "WebSearch":
                suggestion["suggestions"].append({
                    "feature": "Search Result Caching",
                    "description": "Cache search results for quick re-access",
                    "priority": "low"
                })

            if suggestion["suggestions"]:
                suggestions.append(suggestion)

        return suggestions

    def suggest_ux_improvements(self) -> List[Dict]:
        """Suggest UX improvements based on behavior."""
        cursor = self.conn.cursor()

        suggestions = []

        # Check session naming
        unnamed_count = cursor.execute(
            "SELECT COUNT(*) FROM claude_sessions WHERE name IS NULL OR name = ''"
        ).fetchone()[0]

        total_count = cursor.execute("SELECT COUNT(*) FROM claude_sessions").fetchone()[0]

        if unnamed_count > total_count * 0.5:
            suggestions.append({
                "area": "Session Management",
                "issue": f"{unnamed_count}/{total_count} sessions are unnamed",
                "suggestion": {
                    "feature": "Auto-naming with AI",
                    "description": "Use LLM to generate session names from first prompt",
                    "priority": "high",
                    "implementation": "Extract key topics from prompt, generate 2-4 word name"
                }
            })

        # Check session reuse
        single_use = cursor.execute("""
            SELECT COUNT(*) FROM claude_sessions
            WHERE created_at = last_used OR last_used IS NULL
        """).fetchone()[0]

        if single_use > total_count * 0.6:
            suggestions.append({
                "area": "Session Continuity",
                "issue": f"{single_use}/{total_count} sessions used only once",
                "suggestion": {
                    "feature": "Session Suggestions",
                    "description": "Suggest continuing relevant sessions for new prompts",
                    "priority": "medium",
                    "implementation": "Semantic similarity between new prompt and recent sessions"
                }
            })

        # Check for error-prone patterns
        if self.analysis_data and "log_analysis" in self.analysis_data:
            error_count = len(self.analysis_data["log_analysis"].get("error_patterns", {}))
            if error_count > 5:
                suggestions.append({
                    "area": "Error Handling",
                    "issue": f"{error_count} distinct error patterns found",
                    "suggestion": {
                        "feature": "Proactive Error Recovery",
                        "description": "Detect common errors and suggest fixes automatically",
                        "priority": "high",
                        "implementation": "Pattern matching on errors with guided recovery"
                    }
                })

        return suggestions

    def suggest_automation_opportunities(self) -> List[Dict]:
        """Identify tasks that could be automated."""
        cursor = self.conn.cursor()

        # Find sessions close in time with similar prompts (potential workflows)
        sessions = cursor.execute("""
            SELECT
                session_id,
                last_prompt,
                created_at,
                last_used
            FROM claude_sessions
            WHERE last_prompt IS NOT NULL
            ORDER BY created_at DESC
            LIMIT 100
        """).fetchall()

        # Simple temporal clustering
        workflows = []
        current_workflow = []
        last_time = None

        for session in sessions:
            created = datetime.fromisoformat(session["created_at"].replace('Z', '+00:00'))

            if last_time and (last_time - created) < timedelta(hours=1):
                current_workflow.append({
                    "prompt": session["last_prompt"],
                    "time": session["created_at"]
                })
            else:
                if len(current_workflow) >= 3:  # Found a workflow pattern
                    workflows.append(current_workflow)
                current_workflow = [{
                    "prompt": session["last_prompt"],
                    "time": session["created_at"]
                }]

            last_time = created

        suggestions = []

        if workflows:
            for i, workflow in enumerate(workflows[:3], 1):
                suggestions.append({
                    "workflow_id": i,
                    "steps": len(workflow),
                    "suggestion": {
                        "feature": f"Workflow Template #{i}",
                        "description": f"Automate {len(workflow)}-step workflow",
                        "priority": "low",
                        "steps": [w["prompt"][:50] + "..." for w in workflow]
                    }
                })

        return suggestions

    def generate_feature_report(self, output_file: str = None) -> Dict:
        """Generate comprehensive feature suggestion report."""
        self.load_analysis()
        self.connect_db()

        try:
            repeated_patterns = self.analyze_repeated_patterns()
            tool_shortcuts = self.suggest_tool_shortcuts()
            ux_improvements = self.suggest_ux_improvements()
            automation_opportunities = self.suggest_automation_opportunities()

            report = {
                "generated_at": datetime.now().isoformat(),
                "summary": {
                    "repeated_patterns": len(repeated_patterns),
                    "tool_shortcuts": len(tool_shortcuts),
                    "ux_improvements": len(ux_improvements),
                    "automation_opportunities": len(automation_opportunities),
                },
                "suggestions": {
                    "repeated_patterns": repeated_patterns,
                    "tool_shortcuts": tool_shortcuts,
                    "ux_improvements": ux_improvements,
                    "automation_opportunities": automation_opportunities,
                },
                "priority_items": self._prioritize_suggestions(
                    repeated_patterns, tool_shortcuts, ux_improvements
                ),
            }

            if output_file:
                output_path = Path(output_file)
                output_path.parent.mkdir(parents=True, exist_ok=True)

                with open(output_path, 'w') as f:
                    json.dump(report, f, indent=2, default=str)

                print(f"✅ Feature report saved to {output_path}")

            return report

        finally:
            self.close_db()

    def _prioritize_suggestions(self, *suggestion_lists) -> List[Dict]:
        """Extract and prioritize high-priority suggestions."""
        high_priority = []

        for suggestions in suggestion_lists:
            for item in suggestions:
                # Extract suggestion dict
                if "suggestion" in item:
                    suggestion = item["suggestion"]
                    if isinstance(suggestion, dict) and suggestion.get("priority") == "high":
                        high_priority.append(suggestion)

        return high_priority


def print_feature_report(report: Dict):
    """Print formatted feature report."""
    print("\n" + "="*80)
    print("AI-POWERED FEATURE SUGGESTIONS")
    print("="*80)

    print(f"\n📊 Generated: {report['generated_at']}")

    # Summary
    summary = report["summary"]
    print(f"\n📈 Found:")
    print(f"  • {summary['repeated_patterns']} repeated patterns")
    print(f"  • {summary['tool_shortcuts']} tool optimization opportunities")
    print(f"  • {summary['ux_improvements']} UX improvements")
    print(f"  • {summary['automation_opportunities']} automation opportunities")

    # Priority items
    if report["priority_items"]:
        print("\n🔥 HIGH PRIORITY ITEMS")
        print("-" * 80)
        for i, item in enumerate(report["priority_items"], 1):
            print(f"\n{i}. {item['feature']}")
            print(f"   {item['description']}")
            print(f"   💡 Implementation: {item.get('implementation', 'TBD')}")

    # Repeated patterns
    if report["suggestions"]["repeated_patterns"]:
        print("\n🔁 REPEATED PATTERNS → POTENTIAL SHORTCUTS")
        print("-" * 80)
        for item in report["suggestions"]["repeated_patterns"][:5]:
            print(f"\nPattern (used {item['count']}x): {item['pattern']}...")
            sug = item['suggestion']
            print(f"→ {sug['feature']}: {sug['description']}")

    # UX improvements
    if report["suggestions"]["ux_improvements"]:
        print("\n✨ UX IMPROVEMENTS")
        print("-" * 80)
        for item in report["suggestions"]["ux_improvements"]:
            print(f"\n[{item['area']}] {item['issue']}")
            sug = item['suggestion']
            print(f"→ {sug['feature']}: {sug['description']}")

    print("\n" + "="*80)


def main():
    parser = argparse.ArgumentParser(description="AI-powered feature suggestions")
    parser.add_argument(
        "--db",
        default="~/ai_projects/telegram_agent/data/telegram_agent.db",
        help="Path to database"
    )
    parser.add_argument(
        "--analysis",
        help="Path to existing analysis JSON"
    )
    parser.add_argument(
        "--output",
        "-o",
        help="Output file for feature report"
    )
    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Don't print to console"
    )

    args = parser.parse_args()

    db_path = Path(args.db).expanduser()
    analysis_path = Path(args.analysis).expanduser() if args.analysis else None

    suggester = FeatureSuggester(str(db_path), str(analysis_path) if analysis_path else None)
    report = suggester.generate_feature_report(args.output)

    if not args.quiet:
        print_feature_report(report)


if __name__ == "__main__":
    main()
