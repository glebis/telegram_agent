#!/usr/bin/env python3
"""
CLI tool for managing design skills configuration.

Usage:
    python scripts/manage_design_skills.py show          # Show current config
    python scripts/manage_design_skills.py test "build a login form"  # Test skill application
    python scripts/manage_design_skills.py enable impeccable_style    # Enable a skill
    python scripts/manage_design_skills.py disable ui_skills          # Disable a skill
    python scripts/manage_design_skills.py review                     # Get review checklist
"""

import argparse
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.services.design_skills_service import get_design_skills_service
import yaml


def show_config():
    """Display current design skills configuration."""
    service = get_design_skills_service()
    print("\n=== Design Skills Configuration ===\n")

    for skill_name, skill_config in service.config.get("design_skills", {}).items():
        enabled = "✓ ENABLED" if skill_config.get("enabled") else "✗ DISABLED"
        url = skill_config.get("url", "N/A")
        desc = skill_config.get("description", "N/A")

        print(f"{skill_name.upper()}: {enabled}")
        print(f"  URL: {url}")
        print(f"  Description: {desc}")
        print()


def test_skill_application(prompt: str):
    """Test if design skills would be applied to a prompt."""
    service = get_design_skills_service()

    should_apply = service.should_apply_design_skills(prompt)

    print(f"\n=== Testing Prompt ===")
    print(f"Prompt: {prompt}")
    print(f"\nWould apply design skills: {'YES' if should_apply else 'NO'}")

    if should_apply:
        print("\n=== Enhanced System Prompt ===\n")
        enhanced = service.get_enhanced_system_prompt()
        print(enhanced)


def enable_skill(skill_name: str):
    """Enable a design skill."""
    service = get_design_skills_service()

    if skill_name not in service.config.get("design_skills", {}):
        print(f"Error: Skill '{skill_name}' not found")
        print(
            f"Available: {', '.join(service.config.get('design_skills', {}).keys())}"
        )
        return

    # Update config
    service.config["design_skills"][skill_name]["enabled"] = True

    # Save back to file
    with open(service.config_path, "w") as f:
        yaml.dump(service.config, f, default_flow_style=False, sort_keys=False)

    print(f"✓ Enabled {skill_name}")


def disable_skill(skill_name: str):
    """Disable a design skill."""
    service = get_design_skills_service()

    if skill_name not in service.config.get("design_skills", {}):
        print(f"Error: Skill '{skill_name}' not found")
        print(
            f"Available: {', '.join(service.config.get('design_skills', {}).keys())}"
        )
        return

    # Update config
    service.config["design_skills"][skill_name]["enabled"] = False

    # Save back to file
    with open(service.config_path, "w") as f:
        yaml.dump(service.config, f, default_flow_style=False, sort_keys=False)

    print(f"✗ Disabled {skill_name}")


def show_review_checklist():
    """Display the design review checklist."""
    service = get_design_skills_service()

    print("\n=== Design Review Checklist ===\n")
    print(service.get_review_prompt())


def main():
    parser = argparse.ArgumentParser(
        description="Manage design skills for Claude Code integration"
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Show command
    subparsers.add_parser("show", help="Show current configuration")

    # Test command
    test_parser = subparsers.add_parser(
        "test", help="Test if skills apply to a prompt"
    )
    test_parser.add_argument("prompt", help="Prompt to test")

    # Enable command
    enable_parser = subparsers.add_parser("enable", help="Enable a design skill")
    enable_parser.add_argument("skill", help="Skill name to enable")

    # Disable command
    disable_parser = subparsers.add_parser("disable", help="Disable a design skill")
    disable_parser.add_argument("skill", help="Skill name to disable")

    # Review command
    subparsers.add_parser("review", help="Show design review checklist")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    if args.command == "show":
        show_config()
    elif args.command == "test":
        test_skill_application(args.prompt)
    elif args.command == "enable":
        enable_skill(args.skill)
    elif args.command == "disable":
        disable_skill(args.skill)
    elif args.command == "review":
        show_review_checklist()


if __name__ == "__main__":
    main()
