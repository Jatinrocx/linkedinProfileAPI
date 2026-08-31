import unittest
from datetime import timezone
from app.models.profile import ProfileData, ProfileResponse, Location


class TestModels(unittest.TestCase):
    def test_profile_response_scraped_at_timezone(self):
        resp = ProfileResponse(
            url="https://www.linkedin.com/in/test",
            profile=ProfileData(public_id="test", full_name="Test User"),
        )
        self.assertEqual(resp.scraped_at.tzinfo, timezone.utc)

    def test_profile_data_zero_counts(self):
        prof = ProfileData(
            public_id="test",
            connections_count="0",
            followers_count=0,
        )
        self.assertEqual(prof.connections_count, "0")
        self.assertEqual(prof.followers_count, 0)

    def test_location_model(self):
        loc = Location(city="San Francisco", country="United States", full="San Francisco, CA")
        self.assertEqual(loc.city, "San Francisco")
        self.assertEqual(loc.country, "United States")


if __name__ == "__main__":
    unittest.main()
