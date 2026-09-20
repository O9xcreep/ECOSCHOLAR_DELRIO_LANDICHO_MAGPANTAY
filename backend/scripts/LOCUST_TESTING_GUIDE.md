# Locust Load Testing Guide for EcoScholar

This guide explains how to use Locust to generate professional load testing results for Table 26 of your thesis.

## What is Locust?

Locust is an industry-standard Python-based load testing tool used by companies like Spotify, Atlassian, and Google. It provides:
- ✓ Realistic user behavior simulation
- ✓ Web UI for real-time monitoring
- ✓ CSV export for statistical analysis
- ✓ Professional, peer-reviewed results

## Installation

```bash
pip install locust
```

## Quick Start (Windows PowerShell)

### Option 1: Run with Web UI (Interactive)

```powershell
cd backend
locust -f scripts/locustfile.py --host=http://localhost:5000
```

Then open http://localhost:8089 in your browser and configure:
- **Number of users**: 10
- **Spawn rate**: 2 (users per second)
- **Run time**: 60 seconds

### Option 2: Run Headless (Automated)

```powershell
cd backend
python app.py  # Start Flask server first (or in another terminal)

# Then in another terminal:
cd backend
locust -f scripts/locustfile.py `
    --host=http://localhost:5000 `
    --users=10 `
    --spawn-rate=2 `
    --run-time=60s `
    --headless `
    --csv=scripts/locust_results
```

### Option 3: Use the Provided PowerShell Script

```powershell
cd backend/scripts
.\run_locust_test.ps1
```

This automatically:
1. Starts the Flask server
2. Runs Locust with optimal settings
3. Generates CSV results
4. Stops the Flask server

## Analyzing Results

After running Locust, you'll have:
- `locust_results_stats.csv` - Overall statistics
- `locust_results_stats_history.csv` - Timeline data
- `locust_results_failures.csv` - Any failed requests

Parse and format for your thesis:

```bash
python scripts/parse_locust_results.py locust_results
```

This generates `locust_results_summary.json` and prints Table 26 format.

## Test Scenarios

The `locustfile.py` includes two user types:

### 1. EcoScholarUser (Realistic Behavior)
- Wait time: 1-3 seconds between requests
- 5x health checks
- 2x stats requests
- 1x applicants list
- 1x program cycles
- **Realistic think time** (users pause between actions)

### 2. PeakLoadUser (Stress Test)
- Wait time: 0.1-0.5 seconds between requests
- Rapid-fire health checks
- Quick dashboard checks
- **Simulates monitoring systems or peak load**

## Customizing Tests

Edit `locustfile.py` to add more realistic scenarios:

```python
@task(3)
def login_test(self):
    """Simulate login requests."""
    self.client.post("/api/login", json={
        "email": "test@example.com",
        "password": "password123"
    }, name="/api/login")

@task(2)
def upload_document(self):
    """Simulate file upload."""
    with open("test.pdf", "rb") as f:
        self.client.post("/api/upload", files={
            "file": f,
            "applicant_id": "123",
            "document_name": "Test Doc"
        })
```

## For Thesis Documentation

When writing Table 26, cite:
- **Tool**: Locust (locust.io)
- **Version**: 2.46.5+
- **Test Duration**: 60 seconds
- **Concurrent Users**: 10
- **Spawn Rate**: 2 users/second
- **Endpoints Tested**: /api/health, /api/stats, /api/applicants, /api/program-cycles

### Sample Text

> "Response time and throughput testing were conducted using Locust, an industry-standard 
> Python-based load testing framework. The test simulated 10 concurrent users spawning at 
> 2 users per second over a 60-second duration, with realistic think times (1-3 second 
> pauses between user actions). The test harness executed against a local Flask development 
> server. Response times were recorded per-request, and throughput was calculated as the 
> total number of successful requests divided by the total test duration."

## Recommended Test Plan for Thesis

1. **Baseline Test** (Single User)
   - Run 5 sequential requests
   - Measure mean response time
   - Document connection overhead

2. **Standard Load Test** (Recommended for Table 26)
   - 10 concurrent users
   - 60-second duration
   - Realistic behavior patterns

3. **Stress Test** (Optional, for discussion)
   - 50+ concurrent users
   - Find system breaking point
   - Document degradation patterns

## Interpreting Results

- **RPS (Requests/Second)**: Throughput capacity
- **Mean Response Time**: Average user experience
- **Median Response Time**: Typical user experience (better than mean if outliers exist)
- **95th Percentile**: What 95% of users experience (found in stats_history.csv)
- **Success Rate**: Should be 100% for healthy system

## Common Issues

**"Connection refused"**
- Ensure Flask server is running on localhost:5000
- Check: `curl http://localhost:5000/api/health`

**"Too many open connections"**
- Windows limits TCP connections
- Reduce concurrent users to 5-10
- Or increase connection timeout

**"Slow results"**
- This is normal for development environment
- Production with optimizations should be 3-5x faster

## Next Steps

1. Run the test using the PowerShell script
2. Parse results with `parse_locust_results.py`
3. Update Table 26 with real Locust data
4. Update thesis methodology section with tool reference

---

For more information, visit: https://locust.io
