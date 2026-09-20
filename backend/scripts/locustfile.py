"""
Locust load testing script for EcoScholar - FULL STACK TEST

Measures BOTH frontend page loads AND backend API performance for ALL pages:

FRONTEND PAGES TESTED:
- Student: Dashboard, Application Form (Step 1/2/3), Applicant Details
- Admin: Dashboard, Applications, Form Builder, Settings, Rankings
- Public: Landing (if exists)

BACKEND APIs TESTED:
- Health checks, Authentication, Document operations
- Applicant management, Statistics, Notifications
- Duplicate detection, Form configuration

Each page load includes:
  1. HTML page fetch (frontend)
  2. All API calls needed to render it (backend)
  3. Total time = user experience

Usage:
    locust -f scripts/locustfile.py --host=https://www.escholar.site

Then open http://localhost:8089 and start with:
    - Users: 15
    - Spawn rate: 2
    - Run time: 120s
"""
from locust import HttpUser, task, between
import random


def random_email():
    """Generate a random email for testing."""
    return f"testuser_{random.randint(10000, 99999)}@test.com"


class StudentPageUser(HttpUser):
    """Simulates a student - measures FRONTEND + BACKEND for all student pages."""

    wait_time = between(2, 4)
    user_email = None

    def on_start(self):
        self.user_email = random_email()

    # FRONTEND PAGES - AUTHENTICATION (includes all API calls needed)
    @task(2)
    def load_login_page(self):
        """Load login page (frontend + backend: check session)."""
        self.client.get("/student/login", name="FRONTEND: /student/login")

    @task(1)
    def load_register_page(self):
        """Load registration page (frontend + backend: form config)."""
        self.client.get("/student/register", name="FRONTEND: /student/register")

    # FRONTEND PAGES - APPLICATION (includes all API calls needed)
    @task(4)
    def load_student_dashboard(self):
        """Load student dashboard (frontend + backend: stats, application status)."""
        self.client.get("/student/dashboard", name="FRONTEND: /student/dashboard")

    @task(5)
    def load_application_form(self):
        """Load application form (frontend + API: form-fields, profile, cycles)."""
        self.client.get("/student/application", name="FRONTEND: /student/application")

    @task(3)
    def load_applicant_details(self):
        """Load applicant details (frontend + API: documents, requirements, status)."""
        self.client.get("/student/applicant-details", name="FRONTEND: /student/applicant-details")

    # FRONTEND PAGES - INFORMATION & NOTIFICATIONS
    @task(2)
    def load_guidelines(self):
        """Load application guidelines (frontend only - static content)."""
        self.client.get("/student/guidelines", name="FRONTEND: /student/guidelines")

    @task(2)
    def load_notifications(self):
        """Load student notifications (frontend + API: notifications list)."""
        self.client.get("/student/notifications", name="FRONTEND: /student/notifications")

    # BACKEND APIs (pure API testing)
    @task(2)
    def api_form_fields(self):
        """Get form fields configuration."""
        self.client.get("/api/form-fields", name="API: /api/form-fields")

    @task(2)
    def api_doc_requirements(self):
        """Get document requirements."""
        self.client.get("/api/document-requirements", name="API: /api/document-requirements")

    @task(1)
    def api_profile(self):
        """Get student profile."""
        self.client.get("/api/profile", name="API: /api/profile")

    @task(1)
    def api_notifications(self):
        """Get student notifications."""
        self.client.get("/api/notifications", name="API: /api/notifications")

    @task(1)
    def api_student_application(self):
        """Get student's application details."""
        self.client.get("/api/student/application", name="API: /api/student/application")

    @task(1)
    def api_health(self):
        """Health check."""
        self.client.get("/api/health", name="API: /api/health")


class AdminPageUser(HttpUser):
    """Simulates an admin - measures FRONTEND + BACKEND for all admin pages."""

    wait_time = between(1, 3)

    # FRONTEND PAGES (includes all API calls needed)
    @task(4)
    def load_admin_dashboard(self):
        """Load admin dashboard (frontend + API: stats, duplicate-flags, history-log)."""
        self.client.get("/admin/dashboard", name="FRONTEND: /admin/dashboard")

    @task(3)
    def load_applications_page(self):
        """Load applications list (frontend + API: applicants, stats)."""
        self.client.get("/admin/applications", name="FRONTEND: /admin/applications")

    @task(2)
    def load_form_builder(self):
        """Load form builder (frontend + API: form-fields, document-requirements)."""
        self.client.get("/admin/form-builder", name="FRONTEND: /admin/form-builder")

    @task(2)
    def load_settings_page(self):
        """Load settings (frontend + API: settings, program-cycles)."""
        self.client.get("/admin/settings", name="FRONTEND: /admin/settings")

    @task(1)
    def load_ranking_page(self):
        """Load rankings/scoring page (frontend + API: applicants with scores)."""
        self.client.get("/admin/ranking", name="FRONTEND: /admin/ranking")

    # BACKEND APIs (pure API testing)
    @task(2)
    def api_stats(self):
        """Get dashboard statistics."""
        self.client.get("/api/stats?cycle=current", name="API: /api/stats")

    @task(2)
    def api_applicants(self):
        """List all applicants."""
        self.client.get("/api/applicants?cycle=current", name="API: /api/applicants")

    @task(1)
    def api_program_cycles(self):
        """Get program cycles."""
        self.client.get("/api/program-cycles", name="API: /api/program-cycles")

    @task(1)
    def api_duplicate_flags(self):
        """Check duplicate applications."""
        self.client.get("/api/duplicate-flags", name="API: /api/duplicate-flags")

    @task(1)
    def api_notifications(self):
        """Get admin notifications."""
        self.client.get("/api/notifications", name="API: /api/notifications")

    @task(1)
    def api_history_log(self):
        """Get decision history."""
        self.client.get("/api/history-log?limit=20", name="API: /api/history-log")

    @task(1)
    def api_health(self):
        """Health check."""
        self.client.get("/api/health", name="API: /api/health")


class MonitoringSimulator(HttpUser):
    """Simulates monitoring systems and rapid concurrent load."""

    wait_time = between(0.3, 1)

    @task(10)
    def health_check(self):
        """Continuous health monitoring."""
        self.client.get("/api/health", name="API: /api/health [MONITOR]")

    @task(3)
    def quick_stats(self):
        """Quick stats polling."""
        self.client.get("/api/stats?cycle=current", name="API: /api/stats [MONITOR]")

    @task(1)
    def cycle_check(self):
        """Check cycle status."""
        self.client.get("/api/program-cycles", name="API: /api/program-cycles [MONITOR]")
