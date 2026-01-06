#!/bin/bash
# Automated weekly conversation analysis for Telegram Bot
# Run this script weekly to analyze usage patterns and generate feature suggestions

set -e  # Exit on error

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
DATE=$(date +%Y%m%d)
OUTPUT_DIR="$HOME/Research/vault/ai-research"

# Ensure output directory exists
mkdir -p "$OUTPUT_DIR"

echo "🔍 Starting conversation analysis for $(date +%Y-%m-%d)..."
echo "Project: $PROJECT_DIR"
echo "Output: $OUTPUT_DIR"
echo ""

# Step 1: Run conversation analysis
echo "📊 Step 1: Analyzing conversations..."
python3 "$SCRIPT_DIR/analyze_conversations.py" \
  --db "$PROJECT_DIR/data/telegram_agent.db" \
  --log "$PROJECT_DIR/logs/app.log" \
  --output "$OUTPUT_DIR/${DATE}-telegram-analysis.json" \
  --days 7

if [ $? -eq 0 ]; then
    echo "✅ Analysis complete"
else
    echo "❌ Analysis failed"
    exit 1
fi

echo ""

# Step 2: Generate feature suggestions
echo "💡 Step 2: Generating feature suggestions..."
python3 "$SCRIPT_DIR/suggest_features.py" \
  --db "$PROJECT_DIR/data/telegram_agent.db" \
  --analysis "$OUTPUT_DIR/${DATE}-telegram-analysis.json" \
  --output "$OUTPUT_DIR/${DATE}-feature-suggestions.json"

if [ $? -eq 0 ]; then
    echo "✅ Suggestions generated"
else
    echo "❌ Suggestion generation failed"
    exit 1
fi

echo ""

# Step 3: Export conversation data
echo "📤 Step 3: Exporting conversation data..."
python3 "$SCRIPT_DIR/query_conversations.py" \
  --db "$PROJECT_DIR/data/telegram_agent.db" \
  export "$OUTPUT_DIR/${DATE}-conversations-export.json" \
  --limit 100

if [ $? -eq 0 ]; then
    echo "✅ Export complete"
else
    echo "❌ Export failed"
    exit 1
fi

echo ""
echo "="
echo "✅ Weekly analysis complete!"
echo ""
echo "📁 Generated files:"
echo "  - $OUTPUT_DIR/${DATE}-telegram-analysis.json"
echo "  - $OUTPUT_DIR/${DATE}-feature-suggestions.json"
echo "  - $OUTPUT_DIR/${DATE}-conversations-export.json"
echo ""
echo "📊 Quick Stats:"
python3 -c "
import json
with open('$OUTPUT_DIR/${DATE}-telegram-analysis.json') as f:
    data = json.load(f)
    print(f\"  Total sessions: {data['summary']['total_sessions']}\")
    print(f\"  Active sessions: {data['summary']['active_sessions']}\")
    print(f\"  Session reuse rate: {data['summary']['session_reuse_rate']:.1f}%\")

with open('$OUTPUT_DIR/${DATE}-feature-suggestions.json') as f:
    data = json.load(f)
    high_priority = len([s for s in data.get('priority_items', []) if s.get('priority') == 'high'])
    print(f\"  High-priority suggestions: {high_priority}\")
"

echo ""
echo "🔗 Next steps:"
echo "  1. Review suggestions: cat $OUTPUT_DIR/${DATE}-feature-suggestions.json | jq '.priority_items'"
echo "  2. Create GitHub issues for high-priority items"
echo "  3. Update roadmap based on findings"
