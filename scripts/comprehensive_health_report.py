#!/usr/bin/env python3
"""
Comprehensive Weekly Health Report with Graphs
Queries health.db directly for maximum data availability
"""

import sqlite3
import sys
from pathlib import Path
from datetime import datetime, timedelta
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt
import numpy as np

DB_PATH = Path.home() / "data" / "health.db"
OUTPUT_DIR = Path.home() / "Research" / "vault" / "health_reports"
OUTPUT_DIR.mkdir(exist_ok=True)

def get_connection():
    """Connect to health database"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def create_graph(title, dates, values, ylabel, filename, color='#4A90E2'):
    """Create and save a graph"""
    if not dates or not values:
        return None

    plt.figure(figsize=(10, 6))
    plt.style.use('seaborn-v0_8-darkgrid')

    # Plot data
    plt.plot(dates, values, marker='o', linewidth=2, color=color, markersize=8, alpha=0.7)

    # Add trend line
    if len(values) > 1:
        x_numeric = list(range(len(dates)))
        z = np.polyfit(x_numeric, values, 1)
        p = np.poly1d(z)
        plt.plot(dates, p(x_numeric), "--", alpha=0.5, color='red', linewidth=2, label='Trend')

    # Add average line
    avg = np.mean(values)
    plt.axhline(y=avg, color='green', linestyle='--', alpha=0.5, linewidth=2, label=f'Avg: {avg:.1f}')

    plt.xlabel('Date', fontsize=12, fontweight='bold')
    plt.ylabel(ylabel, fontsize=12, fontweight='bold')
    plt.title(title, fontsize=14, fontweight='bold', pad=20)
    plt.xticks(rotation=45, ha='right')
    plt.legend(fontsize=10)
    plt.grid(True, alpha=0.3)
    plt.tight_layout()

    output_path = OUTPUT_DIR / filename
    plt.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close()

    return str(output_path)

def query_daily_metric(record_type, days=7, aggregation='AVG'):
    """Query daily aggregated metric"""
    conn = get_connection()

    query = f"""
    SELECT
        DATE(start_date) as date,
        {aggregation}(value) as value
    FROM health_records
    WHERE record_type = ?
    AND start_date >= date('now', '-{days} days')
    GROUP BY DATE(start_date)
    ORDER BY date ASC
    """

    cursor = conn.execute(query, (record_type,))
    rows = cursor.fetchall()

    dates = [row['date'] for row in rows]
    values = [float(row['value']) for row in rows if row['value']]

    conn.close()
    return dates, values

def query_sleep_data(days=7):
    """Query sleep duration by date"""
    conn = get_connection()

    query = """
    SELECT
        DATE(start_date) as date,
        SUM((julianday(end_date) - julianday(start_date)) * 24) as hours
    FROM health_records
    WHERE record_type = 'HKCategoryTypeIdentifierSleepAnalysis'
    AND value = 2  -- Deep sleep or core sleep
    AND start_date >= date('now', '-{} days')
    GROUP BY DATE(start_date)
    ORDER BY date ASC
    """.format(days)

    cursor = conn.execute(query)
    rows = cursor.fetchall()

    dates = [row['date'] for row in rows]
    hours = [float(row['hours']) for row in rows if row['hours']]

    conn.close()
    return dates, hours

def get_latest_data_timestamp():
    """Get the most recent data timestamp in database"""
    conn = get_connection()
    cursor = conn.execute("""
        SELECT MAX(start_date) as latest FROM health_records
    """)
    row = cursor.fetchone()
    conn.close()
    return row['latest'] if row else None

def generate_report():
    """Generate comprehensive health report"""
    print("=" * 70)
    print("📊 COMPREHENSIVE WEEKLY HEALTH REPORT")
    print("=" * 70)

    report_date = datetime.now().strftime("%Y-%m-%d")
    latest_data = get_latest_data_timestamp()

    print(f"\n📅 Report Generated: {report_date}")
    print(f"📊 Latest Data Available: {latest_data}")

    if latest_data:
        # Parse timezone-aware datetime
        try:
            latest_dt = datetime.fromisoformat(latest_data.split('+')[0].strip())
            data_age = (datetime.now() - latest_dt).days
            if data_age > 1:
                print(f"⚠️  Warning: Data is {data_age} days old. Sync your Apple Watch!")
        except:
            pass

    print(f"\n📁 Output Directory: {OUTPUT_DIR}")
    print("\n" + "-" * 70)

    graphs = []
    stats = []

    # 1. HRV Trend
    print("\n📊 [1/7] Heart Rate Variability...")
    dates, values = query_daily_metric('HKQuantityTypeIdentifierHeartRateVariabilitySDNN', days=14)
    if values:
        graph = create_graph(
            "Heart Rate Variability (14 Days)",
            dates, values,
            "HRV (ms)",
            "1_hrv_trend.png",
            color='#E74C3C'
        )
        if graph:
            graphs.append(graph)
            stats.append(f"📈 HRV: Avg {np.mean(values):.1f} ms (Range: {min(values):.1f}-{max(values):.1f})")
            print(f"   ✓ Avg: {np.mean(values):.1f} ms")

    # 2. Resting Heart Rate
    print("📊 [2/7] Resting Heart Rate...")
    dates, values = query_daily_metric('HKQuantityTypeIdentifierRestingHeartRate', days=14)
    if values:
        graph = create_graph(
            "Resting Heart Rate (14 Days)",
            dates, values,
            "BPM",
            "2_resting_hr.png",
            color='#E67E22'
        )
        if graph:
            graphs.append(graph)
            stats.append(f"❤️  Resting HR: Avg {np.mean(values):.0f} bpm (Range: {min(values):.0f}-{max(values):.0f})")
            print(f"   ✓ Avg: {np.mean(values):.0f} bpm")

    # 3. Daily Steps
    print("📊 [3/7] Daily Steps...")
    dates, values = query_daily_metric('HKQuantityTypeIdentifierStepCount', days=14, aggregation='SUM')
    if values:
        graph = create_graph(
            "Daily Steps (14 Days)",
            dates, values,
            "Steps",
            "3_daily_steps.png",
            color='#3498DB'
        )
        if graph:
            graphs.append(graph)
            stats.append(f"🚶 Steps: Avg {np.mean(values):,.0f}/day (Range: {min(values):,.0f}-{max(values):,.0f})")
            print(f"   ✓ Avg: {np.mean(values):,.0f} steps/day")

    # 4. Active Calories
    print("📊 [4/7] Active Calories...")
    dates, values = query_daily_metric('HKQuantityTypeIdentifierActiveEnergyBurned', days=14, aggregation='SUM')
    if values:
        graph = create_graph(
            "Active Calories Burned (14 Days)",
            dates, values,
            "Calories",
            "4_active_calories.png",
            color='#F39C12'
        )
        if graph:
            graphs.append(graph)
            stats.append(f"🔥 Active Calories: Avg {np.mean(values):.0f}/day")
            print(f"   ✓ Avg: {np.mean(values):.0f} cal/day")

    # 5. Exercise Minutes
    print("📊 [5/7] Exercise Minutes...")
    dates, values = query_daily_metric('HKQuantityTypeIdentifierAppleExerciseTime', days=14, aggregation='SUM')
    if values:
        graph = create_graph(
            "Exercise Minutes (14 Days)",
            dates, values,
            "Minutes",
            "5_exercise_minutes.png",
            color='#16A085'
        )
        if graph:
            graphs.append(graph)
            stats.append(f"🏃 Exercise: Avg {np.mean(values):.0f} min/day")
            print(f"   ✓ Avg: {np.mean(values):.0f} min/day")

    # 6. Distance Walked/Run
    print("📊 [6/7] Distance...")
    dates, values = query_daily_metric('HKQuantityTypeIdentifierDistanceWalkingRunning', days=14, aggregation='SUM')
    if values:
        # Convert meters to km
        values_km = [v / 1000 for v in values]
        graph = create_graph(
            "Walking/Running Distance (14 Days)",
            dates, values_km,
            "Kilometers",
            "6_distance.png",
            color='#9B59B6'
        )
        if graph:
            graphs.append(graph)
            stats.append(f"📏 Distance: Avg {np.mean(values_km):.1f} km/day")
            print(f"   ✓ Avg: {np.mean(values_km):.1f} km/day")

    # 7. Heart Rate (Average Daily)
    print("📊 [7/7] Average Heart Rate...")
    dates, values = query_daily_metric('HKQuantityTypeIdentifierHeartRate', days=14)
    if values:
        graph = create_graph(
            "Average Heart Rate (14 Days)",
            dates, values,
            "BPM",
            "7_avg_heart_rate.png",
            color='#C0392B'
        )
        if graph:
            graphs.append(graph)
            stats.append(f"💓 Avg Heart Rate: {np.mean(values):.0f} bpm")
            print(f"   ✓ Avg: {np.mean(values):.0f} bpm")

    # Summary
    print("\n" + "=" * 70)
    print("📋 SUMMARY")
    print("=" * 70)

    for stat in stats:
        print(f"  {stat}")

    print(f"\n📊 Generated {len(graphs)} graphs")
    print("\n📎 Files:")
    for graph in graphs:
        print(f"  ✓ {Path(graph).name}")

    print("\n" + "=" * 70)

    return graphs, stats, latest_data

if __name__ == "__main__":
    try:
        graphs, stats, latest_data = generate_report()

        if graphs:
            print(f"\n✅ Success! Generated {len(graphs)} health graphs")
            print(f"\n💡 Tip: Open Obsidian vault at {OUTPUT_DIR} to view graphs")
        else:
            print("\n⚠️  No graphs generated. Check database connection.")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
