import os
import unittest
from dotenv import load_dotenv
from fastapi.testclient import TestClient

load_dotenv()

# Ensure dummy values exist for environment testing if .env is missing/empty
if not os.environ.get("LI_AT"):
    os.environ["LI_AT"] = "test_li_at"
if not os.environ.get("JSESSIONID"):
    os.environ["JSESSIONID"] = '"ajax:123456789"'

from app.main import app


class TestAPIEndpoints(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_health_check(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "ok")

    def test_get_profile_invalid_url(self):
        response = self.client.get("/api/profile?url=https://google.com")
        self.assertEqual(response.status_code, 400)

    def test_get_profile_regional_url_validation(self):
        # Checks that regional URL is accepted by validation
        response = self.client.get("/api/profile?url=https://in.linkedin.com/in/jatinbhatt")
        self.assertIn(response.status_code, [200, 401, 502])


if __name__ == "__main__":
    unittest.main()
