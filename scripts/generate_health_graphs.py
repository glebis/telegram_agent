#!/usr/bin/env python3
"""
Generate 7 health status graphs from Apple Health database
"""

import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np

DB_PATH = Path.home() / "data" / "health.db"
OUTPUT_DIR = Path.home() / "Research" / "vault" / "health_reports"
OUTPUT_DIR.mkdir(exist_ok=True, parents=True)

def get_connection():
    """Connect to health database"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def create_graph(title, dates, values, ylabel, filename, color='#4A90E2', target_line=None):
    """Create a matplotlib graph and save it."""
    if not values or all(v is None for v in values):
        print(f"  ⚠️  No data for {title}")
        return None

    plt.figure(figsize=(12, 6))
    plt.style.use('seaborn-v0_8-darkgrid')

    # Convert dates to datetime objects
    date_objs = [datetime.strptime(d, "%Y-%m-%d") if isinstance(d, str) else d for d in dates]

    # Plot main data
    plt.plot(date_objs, values, marker='o', linewidth=2.5, color=color, markersize=8, label='Actual')

    # Add trend line
    if len(values) > 2:
        valid_indices = [i for i, v in enumerate(values) if v is not None]
        if len(valid_indices) > 1:
            valid_x = [i for i in valid_indices]
            valid_y = [values[i] for i in valid_indices]
            z = np.polyfit(valid_x, valid_y, 1)
            p = np.poly1d(z)
            trend_y = [p(i) for i in range(len(values))]
            plt.plot(date_objs, trend_y, "--", alpha=0.6, color='red', linewidth=2, label='Trend')

    # Calculate and show average
    valid_values = [v for v in values if v is not None]
    if valid_values:
        avg = np.mean(valid_values)
        plt.axhline(y=avg, color='green', linestyle='--', alpha=0.7, linewidth=2, label=f'Avg: {avg:.1f}')

    # Add target line if provided
    if target_line:
        plt.axhline(y=target_line, color='orange', linestyle=':', alpha=0.7, linewidth=2, label=f'Target: {target_line}')

    plt.xlabel('Date', fontsize=13, fontweight='bold')
    plt.ylabel(ylabel, fontsize=13, fontweight='bold')
    plt.title(title, fontsize=15, fontweight='bold', pad=20)

    # Format x-axis
    plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%b %d'))
    plt.gca().xaxis.set_major_locator(mdates.DayLocator())
    plt.xticks(rotation=45)

    plt.legend(loc='best', fontsize=11)
    plt.grid(True, alpha=0.3)
    plt.tight_layout()

    output_path = OUTPUT_DIR / filename
    plt.savefig(output_path, dpi=200, bbox_inches='tight')
    plt.close()

    return str(output_path)

def main():
    """Generate 7 health graphs"""
    print("🏥 Generating Health Status Graphs for Last Week\n")

    conn = get_connection()
    graphs = []
    stats = []

    # Get date range (last 7 days)
    end_date = datetime.now()
    start_date = end_date - timedelta(days=6)
    dates = [(start_date + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)]

    print(f"📅 Period: {dates[0]} to {dates[-1]}\n")

    # ==== GRAPH 1: HRV (Heart Rate Variability) ====
    print("📊 1/7: HRV Trend...")
    cursor = conn.execute("""
        SELECT DATE(SUBSTR(start_date, 1, 10)) as date, AVG(value) as avg_hrv
        FROM health_records
        WHERE record_type = 'HKQuantityTypeIdentifierHeartRateVariabilitySDNN'
        AND DATE(SUBSTR(start_date, 1, 10)) >= ?
        AND DATE(SUBSTR(start_date, 1, 10)) <= ?
        GROUP BY DATE(SUBSTR(start_date, 1, 10))
        ORDER BY date
    """, (dates[0], dates[-1]))

    hrv_data = {row['date']: round(row['avg_hrv'], 1) if row['avg_hrv'] else None for row in cursor.fetchall()}
    hrv_values = [hrv_data.get(d) for d in dates]

    if any(v for v in hrv_values):
        graph = create_graph(
            "💓 Heart Rate Variability (HRV) - 7 Day Trend",
            dates, hrv_values, "HRV (ms)", "1_hrv_trend.png", color='#E74C3C', target_line=60
        )
        if graph:
            graphs.append(graph)
            avg_hrv = np.mean([v for v in hrv_values if v])
            stats.append(f"📈 HRV Avg: {avg_hrv:.1f} ms")

    # ==== GRAPH 2: Sleep Duration ====
    print("📊 2/7: Sleep Duration...")
    cursor = conn.execute("""
        SELECT DATE(SUBSTR(start_date, 1, 10)) as date, SUM(value) / 60.0 as hours
        FROM health_records
        WHERE record_type = 'HKCategoryTypeIdentifierSleepAnalysis'
        AND DATE(SUBSTR(start_date, 1, 10)) >= ?
        AND DATE(SUBSTR(start_date, 1, 10)) <= ?
        GROUP BY DATE(SUBSTR(start_date, 1, 10))
        ORDER BY date
    """, (dates[0], dates[-1]))

    sleep_data = {row['date']: round(row['hours'], 1) if row['hours'] else None for row in cursor.fetchall()}
    sleep_values = [sleep_data.get(d) for d in dates]

    if any(v for v in sleep_values):
        graph = create_graph(
            "😴 Sleep Duration - 7 Day Trend",
            dates, sleep_values, "Hours", "2_sleep_duration.png", color='#9B59B6', target_line=8
        )
        if graph:
            graphs.append(graph)
            avg_sleep = np.mean([v for v in sleep_values if v])
            stats.append(f"😴 Sleep Avg: {avg_sleep:.1f} hours")

    # ==== GRAPH 3: Resting Heart Rate ====
    print("📊 3/7: Resting Heart Rate...")
    cursor = conn.execute("""
        SELECT DATE(SUBSTR(start_date, 1, 10)) as date, AVG(value) as avg_rhr
        FROM health_records
        WHERE record_type = 'HKQuantityTypeIdentifierRestingHeartRate'
        AND DATE(SUBSTR(start_date, 1, 10)) >= ?
        AND DATE(SUBSTR(start_date, 1, 10)) <= ?
        GROUP BY DATE(SUBSTR(start_date, 1, 10))
        ORDER BY date
    """, (dates[0], dates[-1]))

    rhr_data = {row['date']: round(row['avg_rhr'], 0) if row['avg_rhr'] else None for row in cursor.fetchall()}
    rhr_values = [rhr_data.get(d) for d in dates]

    if any(v for v in rhr_values):
        graph = create_graph(
            "❤️ Resting Heart Rate - 7 Day Trend",
            dates, rhr_values, "BPM", "3_resting_hr.png", color='#E67E22', target_line=60
        )
        if graph:
            graphs.append(graph)
            avg_rhr = np.mean([v for v in rhr_values if v])
            stats.append(f"❤️ Resting HR Avg: {avg_rhr:.0f} bpm")

    # ==== GRAPH 4: Daily Steps ====
    print("📊 4/7: Daily Steps...")
    cursor = conn.execute("""
        SELECT DATE(SUBSTR(start_date, 1, 10)) as date, SUM(value) as total_steps
        FROM health_records
        WHERE record_type = 'HKQuantityTypeIdentifierStepCount'
        AND DATE(SUBSTR(start_date, 1, 10)) >= ?
        AND DATE(SUBSTR(start_date, 1, 10)) <= ?
        GROUP BY DATE(SUBSTR(start_date, 1, 10))
        ORDER BY date
    """, (dates[0], dates[-1]))

    steps_data = {row['date']: int(row['total_steps']) for row in cursor.fetchall()}
    steps_values = [steps_data.get(d) for d in dates]

    if any(v for v in steps_values):
        graph = create_graph(
            "🚶 Daily Steps - 7 Day Trend",
            dates, steps_values, "Steps", "4_daily_steps.png", color='#3498DB', target_line=10000
        )
        if graph:
            graphs.append(graph)
            avg_steps = np.mean([v for v in steps_values if v])
            stats.append(f"🚶 Steps Avg: {avg_steps:,.0f}")

    # ==== GRAPH 5: Blood Oxygen ====
    print("📊 5/7: Blood Oxygen...")
    cursor = conn.execute("""
        SELECT DATE(SUBSTR(start_date, 1, 10)) as date, AVG(value * 100) as avg_spo2
        FROM health_records
        WHERE record_type = 'HKQuantityTypeIdentifierOxygenSaturation'
        AND DATE(SUBSTR(start_date, 1, 10)) >= ?
        AND DATE(SUBSTR(start_date, 1, 10)) <= ?
        GROUP BY DATE(SUBSTR(start_date, 1, 10))
        ORDER BY date
    """, (dates[0], dates[-1]))

    spo2_data = {row['date']: round(row['avg_spo2'], 1) if row['avg_spo2'] else None for row in cursor.fetchall()}
    spo2_values = [spo2_data.get(d) for d in dates]

    if any(v for v in spo2_values):
        graph = create_graph(
            "🫁 Blood Oxygen Saturation - 7 Day Trend",
            dates, spo2_values, "SpO2 (%)", "5_blood_oxygen.png", color='#1ABC9C', target_line=95
        )
        if graph:
            graphs.append(graph)
            avg_spo2 = np.mean([v for v in spo2_values if v])
            stats.append(f"🫁 Blood O2 Avg: {avg_spo2:.1f}%")

    # ==== GRAPH 6: Exercise Minutes ====
    print("📊 6/7: Exercise Minutes...")
    cursor = conn.execute("""
        SELECT DATE(SUBSTR(start_date, 1, 10)) as date, SUM(value) as total_mins
        FROM health_records
        WHERE record_type = 'HKQuantityTypeIdentifierAppleExerciseTime'
        AND DATE(SUBSTR(start_date, 1, 10)) >= ?
        AND DATE(SUBSTR(start_date, 1, 10)) <= ?
        GROUP BY DATE(SUBSTR(start_date, 1, 10))
        ORDER BY date
    """, (dates[0], dates[-1]))

    exercise_data = {row['date']: int(row['total_mins']) for row in cursor.fetchall()}
    exercise_values = [exercise_data.get(d) for d in dates]

    if any(v for v in exercise_values):
        graph = create_graph(
            "🏃 Exercise Minutes - 7 Day Trend",
            dates, exercise_values, "Minutes", "6_exercise_minutes.png", color='#16A085', target_line=30
        )
        if graph:
            graphs.append(graph)
            avg_exercise = np.mean([v for v in exercise_values if v])
            stats.append(f"🏃 Exercise Avg: {avg_exercise:.0f} min/day")

    # ==== GRAPH 7: Active Calories ====
    print("📊 7/7: Active Calories...")
    cursor = conn.execute("""
        SELECT DATE(SUBSTR(start_date, 1, 10)) as date, SUM(value) as total_cals
        FROM health_records
        WHERE record_type = 'HKQuantityTypeIdentifierActiveEnergyBurned'
        AND DATE(SUBSTR(start_date, 1, 10)) >= ?
        AND DATE(SUBSTR(start_date, 1, 10)) <= ?
        GROUP BY DATE(SUBSTR(start_date, 1, 10))
        ORDER BY date
    """, (dates[0], dates[-1]))

    cal_data = {row['date']: int(row['total_cals']) for row in cursor.fetchall()}
    cal_values = [cal_data.get(d) for d in dates]

    if any(v for v in cal_values):
        graph = create_graph(
            "🔥 Active Calories Burned - 7 Day Trend",
            dates, cal_values, "Calories (kcal)", "7_active_calories.png", color='#F39C12', target_line=500
        )
        if graph:
            graphs.append(graph)
            avg_cals = np.mean([v for v in cal_values if v])
            stats.append(f"🔥 Active Calories Avg: {avg_cals:.0f} kcal")

    conn.close()

    # Print summary
    print("\n" + "="*70)
    print("📊 WEEKLY HEALTH SUMMARY")
    print("="*70)
    print(f"📅 Week: {dates[0]} to {dates[-1]}")
    print(f"📈 Graphs Generated: {len(graphs)}/7\n")

    for stat in stats:
        print(f"  {stat}")

    print(f"\n📁 Saved to: {OUTPUT_DIR}")
    print("="*70)

    # List files
    print("\n📎 Generated Files:")
    for g in graphs:
        print(f"  ✓ {Path(g).name}")

    return graphs

if __name__ == "__main__":
    try:
        graphs = main()
        print(f"\n✅ Complete! Generated {len(graphs)} graphs.\n")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
