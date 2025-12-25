#!/usr/bin/env python3
"""
Weekly Health Report - Generate comprehensive health trends with graphs.
"""

import sys
import json
import subprocess
from pathlib import Path
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np

# Health script path
HEALTH_SCRIPT = Path.home() / ".claude" / "skills" / "health-data" / "scripts" / "health_query.py"
OUTPUT_DIR = Path.home() / "Research" / "vault" / "health_reports"
OUTPUT_DIR.mkdir(exist_ok=True)

def query_health_data(query_type: str, *args) -> dict:
    """Query health data using health_query.py script."""
    cmd = ["python3", str(HEALTH_SCRIPT), "--format", "json", query_type] + list(args)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode == 0:
        return json.loads(result.stdout)
    return {}

def create_graph(title, x_data, y_data, ylabel, filename, color='#4A90E2', trend_line=True):
    """Create a matplotlib graph and save it."""
    plt.figure(figsize=(10, 6))
    plt.style.use('seaborn-v0_8-darkgrid')

    # Plot main data
    plt.plot(x_data, y_data, marker='o', linewidth=2, color=color, markersize=6)

    # Add trend line
    if trend_line and len(x_data) > 1:
        z = np.polyfit(range(len(x_data)), y_data, 1)
        p = np.poly1d(z)
        plt.plot(x_data, p(range(len(x_data))), "--", alpha=0.5, color='red', label='Trend')

    # Calculate stats
    avg = np.mean(y_data)
    plt.axhline(y=avg, color='green', linestyle='--', alpha=0.5, label=f'Avg: {avg:.1f}')

    plt.xlabel('Date', fontsize=12)
    plt.ylabel(ylabel, fontsize=12)
    plt.title(title, fontsize=14, fontweight='bold')
    plt.xticks(rotation=45)
    plt.legend()
    plt.tight_layout()

    output_path = OUTPUT_DIR / filename
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()

    return str(output_path)

def generate_weekly_report():
    """Generate comprehensive weekly health report with 7 graphs."""
    print("🔍 Generating Weekly Health Report...\n")

    # Get data for last 7 days
    today = datetime.now()
    dates = [(today - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(6, -1, -1)]
    date_labels = [(today - timedelta(days=i)).strftime("%b %d") for i in range(6, -1, -1)]

    graphs = []
    report_lines = []

    # 1. HRV Trend (7 days)
    print("📊 Graph 1/7: HRV Trend...")
    vitals_data = query_health_data("vitals", "--days", "7")
    if vitals_data and 'daily_vitals' in vitals_data:
        hrv_values = []
        hrv_dates = []
        for day in vitals_data['daily_vitals']:
            if 'HRV' in day:
                hrv_values.append(float(day['HRV']['value']))
                hrv_dates.append(day['date'])

        if hrv_values:
            graph = create_graph(
                "Heart Rate Variability (7 Days)",
                hrv_dates[-7:],
                hrv_values[-7:],
                "HRV (ms)",
                "1_hrv_trend.png",
                color='#E74C3C'
            )
            graphs.append(graph)
            report_lines.append(f"📈 **HRV Avg**: {np.mean(hrv_values):.1f} ms")

    # 2. Sleep Duration Trend
    print("📊 Graph 2/7: Sleep Duration...")
    sleep_data = query_health_data("sleep", "--days", "7")
    if sleep_data and 'nights' in sleep_data:
        sleep_hours = []
        sleep_dates = []
        for night in sleep_data['nights'][:7]:
            sleep_hours.append(night['duration_hours'])
            sleep_dates.append(night['date'])

        if sleep_hours:
            graph = create_graph(
                "Sleep Duration (7 Days)",
                sleep_dates,
                sleep_hours,
                "Hours",
                "2_sleep_duration.png",
                color='#9B59B6'
            )
            graphs.append(graph)
            report_lines.append(f"😴 **Sleep Avg**: {np.mean(sleep_hours):.1f} hours")

    # 3. Resting Heart Rate
    print("📊 Graph 3/7: Resting Heart Rate...")
    if vitals_data and 'daily_vitals' in vitals_data:
        rhr_values = []
        rhr_dates = []
        for day in vitals_data['daily_vitals']:
            if 'Resting HR' in day:
                rhr_values.append(float(day['Resting HR']['value']))
                rhr_dates.append(day['date'])

        if rhr_values:
            graph = create_graph(
                "Resting Heart Rate (7 Days)",
                rhr_dates[-7:],
                rhr_values[-7:],
                "BPM",
                "3_resting_hr.png",
                color='#E67E22'
            )
            graphs.append(graph)
            report_lines.append(f"❤️ **Resting HR Avg**: {np.mean(rhr_values):.0f} bpm")

    # 4. Daily Steps
    print("📊 Graph 4/7: Daily Steps...")
    activity_data = query_health_data("activity", "--days", "7")
    if activity_data and 'days' in activity_data:
        steps = []
        step_dates = []
        for day in activity_data['days'][:7]:
            if 'steps' in day:
                steps.append(day['steps'])
                step_dates.append(day['date'])

        if steps:
            graph = create_graph(
                "Daily Steps (7 Days)",
                step_dates,
                steps,
                "Steps",
                "4_daily_steps.png",
                color='#3498DB'
            )
            graphs.append(graph)
            report_lines.append(f"🚶 **Steps Avg**: {np.mean(steps):,.0f}")

    # 5. Deep Sleep Trend
    print("📊 Graph 5/7: Deep Sleep...")
    if sleep_data and 'nights' in sleep_data:
        deep_sleep = []
        deep_dates = []
        for night in sleep_data['nights'][:7]:
            stages = night.get('sleep_stages', {})
            if 'Deep' in stages:
                # Extract hours from "Xh Ym" format
                deep_str = stages['Deep']
                hours = 0
                if 'h' in deep_str:
                    parts = deep_str.split()
                    hours = float(parts[0].replace('h', ''))
                    if len(parts) > 1 and 'm' in parts[1]:
                        hours += float(parts[1].replace('m', '')) / 60
                deep_sleep.append(hours)
                deep_dates.append(night['date'])

        if deep_sleep:
            graph = create_graph(
                "Deep Sleep (7 Days)",
                deep_dates,
                deep_sleep,
                "Hours",
                "5_deep_sleep.png",
                color='#1ABC9C'
            )
            graphs.append(graph)
            report_lines.append(f"🌙 **Deep Sleep Avg**: {np.mean(deep_sleep):.1f} hours")

    # 6. REM Sleep Trend
    print("📊 Graph 6/7: REM Sleep...")
    if sleep_data and 'nights' in sleep_data:
        rem_sleep = []
        rem_dates = []
        for night in sleep_data['nights'][:7]:
            stages = night.get('sleep_stages', {})
            if 'REM' in stages:
                rem_str = stages['REM']
                hours = 0
                if 'h' in rem_str:
                    parts = rem_str.split()
                    hours = float(parts[0].replace('h', ''))
                    if len(parts) > 1 and 'm' in parts[1]:
                        hours += float(parts[1].replace('m', '')) / 60
                rem_sleep.append(hours)
                rem_dates.append(night['date'])

        if rem_sleep:
            graph = create_graph(
                "REM Sleep (7 Days)",
                rem_dates,
                rem_sleep,
                "Hours",
                "6_rem_sleep.png",
                color='#F39C12'
            )
            graphs.append(graph)
            report_lines.append(f"💤 **REM Sleep Avg**: {np.mean(rem_sleep):.1f} hours")

    # 7. Exercise Minutes
    print("📊 Graph 7/7: Exercise Minutes...")
    if activity_data and 'days' in activity_data:
        exercise_mins = []
        exercise_dates = []
        for day in activity_data['days'][:7]:
            if 'exercise_minutes' in day:
                exercise_mins.append(day['exercise_minutes'])
                exercise_dates.append(day['date'])

        if exercise_mins:
            graph = create_graph(
                "Exercise Minutes (7 Days)",
                exercise_dates,
                exercise_mins,
                "Minutes",
                "7_exercise_mins.png",
                color='#16A085'
            )
            graphs.append(graph)
            report_lines.append(f"🏃 **Exercise Avg**: {np.mean(exercise_mins):.0f} min/day")

    # Generate summary report
    print("\n" + "="*60)
    print("📊 WEEKLY HEALTH SUMMARY")
    print("="*60)

    report_text = f"\n**Week of {dates[0]} to {dates[-1]}**\n\n"
    report_text += "\n".join(report_lines)
    report_text += f"\n\n📁 **Graphs saved to**: {OUTPUT_DIR}"
    report_text += f"\n📈 **Total graphs generated**: {len(graphs)}"

    print(report_text)
    print("\n" + "="*60)

    # List generated files
    print("\n📎 Generated Files:")
    for graph in graphs:
        print(f"  ✓ {Path(graph).name}")

    return graphs, report_text

if __name__ == "__main__":
    try:
        graphs, report = generate_weekly_report()
        print(f"\n✅ Report complete! Generated {len(graphs)} graphs.")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
