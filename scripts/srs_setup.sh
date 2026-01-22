#!/bin/bash
# SRS System Setup Script
# Initializes the spaced repetition system for telegram_agent

set -e

echo "🚀 Setting up SRS (Spaced Repetition System)"
echo ""

# Paths
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SRS_DIR="$PROJECT_ROOT/src/services/srs"
DB_DIR="$PROJECT_ROOT/data/srs"
DB_PATH="$DB_DIR/schedule.db"
SCHEMA_PATH="$DB_DIR/schema.sql"

# Step 1: Check dependencies
echo "📦 Checking dependencies..."
command -v python3 >/dev/null 2>&1 || { echo "❌ python3 required but not installed"; exit 1; }
command -v sqlite3 >/dev/null 2>&1 || { echo "❌ sqlite3 required but not installed"; exit 1; }

python3 -c "import yaml" 2>/dev/null || { echo "❌ PyYAML required: pip3 install pyyaml"; exit 1; }

echo "✅ Dependencies OK"
echo ""

# Step 2: Create database
echo "🗄️  Creating database..."
mkdir -p "$DB_DIR"

if [ -f "$DB_PATH" ]; then
    read -p "Database exists. Recreate? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        rm "$DB_PATH"
        sqlite3 "$DB_PATH" < "$SCHEMA_PATH"
        echo "✅ Database recreated"
    else
        echo "⏭️  Using existing database"
    fi
else
    sqlite3 "$DB_PATH" < "$SCHEMA_PATH"
    echo "✅ Database created"
fi
echo ""

# Step 3: Configure
echo "⚙️  Configuration"
read -p "Morning batch time (HH:MM, default 09:00): " batch_time
batch_time=${batch_time:-09:00}

read -p "Morning batch size (default 5): " batch_size
batch_size=${batch_size:-5}

read -p "Your Telegram chat ID (check with /start): " chat_id

cd "$SRS_DIR"
python3 srs_scheduler.py --config morning_batch_time "$batch_time"
python3 srs_scheduler.py --config morning_batch_size "$batch_size"
if [ -n "$chat_id" ]; then
    python3 srs_scheduler.py --config telegram_chat_id "$chat_id"
fi

echo "✅ Configuration saved"
echo ""

# Step 4: Seed ideas
echo "🌱 Seeding evergreen ideas..."
read -p "Run dry-run first? (Y/n): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Nn]$ ]]; then
    python3 srs_seed.py --dry-run
    echo ""
    read -p "Proceed with actual seeding? (Y/n): " -n 1 -r
    echo
fi

if [[ ! $REPLY =~ ^[Nn]$ ]]; then
    python3 srs_seed.py
    echo "✅ Ideas seeded"
else
    echo "⏭️  Skipping seeding"
fi
echo ""

# Step 5: Initial sync
echo "🔄 Syncing vault to database..."
python3 srs_sync.py -v
echo ""

# Step 6: Show stats
echo "📊 Current status:"
sqlite3 "$DB_PATH" <<EOF
SELECT
    note_type,
    COUNT(*) as total,
    SUM(CASE WHEN is_due = 1 THEN 1 ELSE 0 END) as due_now
FROM srs_cards
WHERE srs_enabled = 1
GROUP BY note_type;
EOF
echo ""

# Step 7: Next steps
echo "⏰ Next steps:"
echo ""
echo "1. The SRS handlers are in: src/bot/handlers/srs_handlers.py"
echo "   Make sure they're registered in your main bot file."
echo ""
echo "2. Add to crontab (crontab -e):"
echo ""
echo "   # Sync vault every hour"
echo "   0 * * * * cd $SRS_DIR && python3 srs_sync.py"
echo ""
echo "   # Send morning batch via bot (implement in main.py)"
echo "   0 9 * * * python3 $PROJECT_ROOT/scripts/send_morning_batch.py"
echo ""
echo "3. Test with: /review in Telegram"
echo ""
echo "4. See README.md for full documentation"
echo ""

echo "✅ Setup complete!"
