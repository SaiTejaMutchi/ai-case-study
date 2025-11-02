#!/bin/bash
echo "🚀 Setting up the Appliance Assistant environment..."
PROJECT_ROOT=$(pwd)

# === BACKEND SETUP ===
echo "📦 Setting up Python backend..."
cd backend || exit

# Create virtual environment if not already present
if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi

# Install dependencies
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
cd "$PROJECT_ROOT"

# === FRONTEND SETUP ===
cd frontend || exit
echo "📦 Installing frontend dependencies..."
npm install
cd "$PROJECT_ROOT"

# === LAUNCH TERMINALS ===
echo "🧠 Launching Backend and Frontend in separate Terminal windows..."

# Launch backend in new Terminal window
osascript <<EOF
tell application "Terminal"
    do script "cd '$PROJECT_ROOT/backend' && source .venv/bin/activate && uvicorn app:app --host 127.0.0.1 --port 8000 --reload"
    activate
end tell
EOF


# Give backend a few seconds to start
sleep 4

# Launch frontend in another Terminal window
osascript <<EOF
tell application "Terminal"
    do script "cd '$PROJECT_ROOT/frontend' && npm run dev"
    activate
end tell
EOF

# Give frontend time to start
sleep 5

# Open frontend in default browser
echo "🌐 Opening frontend in your browser..."
open http://localhost:5173

echo ""
echo "✅ Setup complete! Both servers are now running in separate Terminal windows."
echo ""
echo "🧠 Backend:  http://127.0.0.1:8000/docs"
echo "💻 Frontend: http://localhost:5173"
echo ""
echo "📄 If either crashes, check their Terminal tabs for logs."
echo ""
