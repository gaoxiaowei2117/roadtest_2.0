#!/usr/bin/env python3
"""
Token manager for caching and reusing authentication tokens
"""

import logging
import time
from datetime import datetime, timedelta
from playwright_login import get_weblogin_playwright


class TokenManager:
    def __init__(self, config):
        """
        Initialize token manager

        Args:
            config: Configuration dictionary
        """
        self.config = config
        self.cached_token = None
        self.cached_response_data = None  # Cache full response data including webAappointments
        self.token_expiry = None
        self.token_lifetime = 4 * 60  # 4 minutes (token valid for ~5 min, use 4 to be safe)

    def get_valid_token(self, headless=True):
        """
        Get a valid authentication token (from cache or by logging in)

        Args:
            headless: Whether to run browser in headless mode

        Returns:
            Mock response object with Authorization header, or None if failed
        """
        # Check if we have a cached token that's still valid
        if self.is_token_valid():
            logging.info("✅ Using cached token (still valid)")
            return self._create_response(self.cached_token, self.cached_response_data)

        # Token expired or doesn't exist, need to login
        if self.cached_token:
            logging.info("🔄 Token expired, logging in again...")
        else:
            logging.info("🔑 No token cached, performing initial login...")

        # Perform login
        response = get_weblogin_playwright(self.config, headless=headless)

        if response:
            # Cache the token and response data
            self.cached_token = response.headers.get('Authorization', '')
            self.cached_response_data = response.json()  # Cache full response including webAappointments
            self.token_expiry = datetime.now() + timedelta(seconds=self.token_lifetime)

            expiry_str = self.token_expiry.strftime("%H:%M:%S")
            logging.info(f"✅ New token cached (valid until {expiry_str})")

            return response
        else:
            logging.error("❌ Login failed, could not get token")
            return None

    def is_token_valid(self):
        """
        Check if cached token is still valid

        Returns:
            bool: True if token exists and hasn't expired
        """
        if not self.cached_token or not self.token_expiry:
            return False

        return datetime.now() < self.token_expiry

    def invalidate_token(self):
        """
        Manually invalidate the cached token (e.g., after 401 error)
        """
        logging.info("⚠️  Invalidating cached token")
        self.cached_token = None
        self.cached_response_data = None
        self.token_expiry = None

    def _create_response(self, token, response_data=None):
        """
        Create a mock response object with the token

        Args:
            token: Authorization token string
            response_data: Full response data (including webAappointments if available)

        Returns:
            Mock response object
        """
        class MockResponse:
            def __init__(self, token, response_data, config):
                self.status_code = 200
                self.headers = {'Authorization': token}
                # Use cached response data if available, otherwise create minimal data
                if response_data:
                    self._json_data = response_data
                else:
                    self._json_data = {'drvrId': config.get('icbc', {}).get('drvrID', '')}

            def json(self):
                return self._json_data

        return MockResponse(token, response_data, self.config)

    def get_token_stats(self):
        """
        Get statistics about token usage

        Returns:
            dict: Token statistics
        """
        if not self.cached_token:
            return {
                'has_token': False,
                'is_valid': False,
                'time_remaining': 0
            }

        is_valid = self.is_token_valid()
        time_remaining = 0

        if is_valid:
            time_remaining = (self.token_expiry - datetime.now()).total_seconds()

        return {
            'has_token': True,
            'is_valid': is_valid,
            'time_remaining': int(time_remaining),
            'expiry_time': self.token_expiry.strftime("%H:%M:%S") if self.token_expiry else None
        }


# For testing
if __name__ == "__main__":
    import yaml

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    with open('config.yml', 'r') as f:
        config = yaml.safe_load(f)

    manager = TokenManager(config)

    # Test 1: First call should login
    print("\n" + "="*70)
    print("Test 1: First call (should login)")
    print("="*70)
    response1 = manager.get_valid_token(headless=True)
    if response1:
        print(f"✅ Got token: {response1.headers['Authorization'][:80]}...")
        stats = manager.get_token_stats()
        print(f"   Valid for: {stats['time_remaining']} seconds")
    else:
        print("❌ Failed to get token")

    # Test 2: Immediate second call should use cache
    print("\n" + "="*70)
    print("Test 2: Immediate second call (should use cache)")
    print("="*70)
    response2 = manager.get_valid_token(headless=True)
    if response2:
        print(f"✅ Got token from cache")
        stats = manager.get_token_stats()
        print(f"   Valid for: {stats['time_remaining']} seconds")

    # Test 3: Wait a bit and check
    print("\n" + "="*70)
    print("Test 3: After 5 seconds (should still use cache)")
    print("="*70)
    time.sleep(5)
    response3 = manager.get_valid_token(headless=True)
    if response3:
        print(f"✅ Got token from cache")
        stats = manager.get_token_stats()
        print(f"   Valid for: {stats['time_remaining']} seconds")

    print("\n" + "="*70)
    print("✅ Token Manager Test Complete")
    print("="*70)
