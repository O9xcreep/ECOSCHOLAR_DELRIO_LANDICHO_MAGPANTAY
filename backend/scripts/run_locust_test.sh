#!/bin/bash
# Run Locust load testing for EcoScholar API and generate results

echo "======================================================================"
echo "EcoScholar API Load Testing with Locust"
echo "======================================================================"
echo ""
echo "Starting Flask server in background..."
cd "$(dirname "$0")/.."
python app.py &
APP_PID=$!
sleep 3

echo "Flask server started (PID: $APP_PID)"
echo ""
echo "Running Locust test..."
echo "Test configuration:"
echo "  - Users: 10"
echo "  - Spawn rate: 2 users/sec"
echo "  - Duration: 60 seconds"
echo ""

# Run Locust in headless mode and capture CSV results
locust -f scripts/locustfile.py \
    --host=http://localhost:5000 \
    --users=10 \
    --spawn-rate=2 \
    --run-time=60s \
    --headless \
    --csv=scripts/locust_results

echo ""
echo "======================================================================"
echo "Test Complete!"
echo "======================================================================"
echo ""
echo "Results saved to:"
echo "  - scripts/locust_results_stats.csv (statistics)"
echo "  - scripts/locust_results_stats_history.csv (timeline)"
echo "  - scripts/locust_results_failures.csv (failures, if any)"
echo ""
echo "Shutting down Flask server..."
kill $APP_PID
wait $APP_PID 2>/dev/null

echo "Done!"
