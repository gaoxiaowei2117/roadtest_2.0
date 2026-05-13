#!/usr/bin/env python3
"""
Playwright-based login module for ICBC DEAS system
Replaces the old API-based login with browser automation to handle KBA authentication
"""

import asyncio
import logging
from playwright.async_api import async_playwright


class PlaywrightLogin:
    def __init__(self, config):
        """
        Initialize with configuration

        Args:
            config: Dictionary containing ICBC configuration (drvrLastName, licenceNumber, keyword, DateOfIssue)
        """
        self.config = config
        self.icbc = config.get('icbc', {})
        self.captured_token = None
        self.captured_response_data = None

    async def _handle_request(self, request):
        """Request handler to capture Authorization token"""
        auth_header = request.headers.get('authorization') or request.headers.get('Authorization')
        if auth_header and auth_header.startswith('Bearer'):
            self.captured_token = auth_header
            logging.debug(f"Captured token from request to: {request.url}")

    async def _handle_response(self, response):
        """Response handler to capture login response data"""
        # Look for login-related API responses that contain appointment data
        if 'deas-api' in response.url and response.status == 200:
            try:
                response_json = await response.json()
                # Store the full response data including webAappointments
                if response_json:
                    self.captured_response_data = response_json
                    logging.info(f"📥 Captured API response from: {response.url}")
                    if 'webAappointments' in response_json:
                        logging.info(f"✅ Found webAappointments in response: {len(response_json['webAappointments'])} appointments")
                    else:
                        logging.info(f"ℹ️  Response keys: {list(response_json.keys())}")
            except Exception as e:
                logging.debug(f"Could not parse response from {response.url}: {e}")

    async def login_and_get_token(self, headless=True):
        """
        Perform browser-based login and extract Authorization token

        Args:
            headless: Whether to run browser in headless mode (default: True)

        Returns:
            str: Authorization Bearer token, or None if login failed
        """
        logging.info("Starting Playwright-based login...")

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=headless)
            context = await browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36',
                locale='en-CA',
                timezone_id='America/Vancouver'
            )

            page = await context.new_page()

            # Set up request listener to capture token
            page.on("request", self._handle_request)

            # Set up response listener to capture login response data
            page.on("response", self._handle_response)

            try:
                # Step 1: Navigate to home page
                logging.info("Navigating to ICBC home page...")
                await page.goto("https://onlinebusiness.icbc.com/webdeas-ui/home",
                              wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(3)

                # Step 2: Accept terms
                logging.info("Accepting terms and conditions...")
                await page.check('input[type="checkbox"]')
                await asyncio.sleep(1)

                # Step 3: Click Sign in (third Sign in button for driver's licence login)
                logging.info("Clicking Sign in (3rd button for driver's licence)...")
                sign_in_buttons = await page.locator('button:has-text("Sign in")').all()
                if len(sign_in_buttons) >= 3:
                    await sign_in_buttons[2].click()  # Index 2 = third button
                    logging.info(f"Clicked 3rd Sign in button (found {len(sign_in_buttons)} buttons)")
                elif len(sign_in_buttons) > 0:
                    logging.warning(f"Only found {len(sign_in_buttons)} Sign in buttons, clicking the last one")
                    await sign_in_buttons[-1].click()
                else:
                    logging.error("No Sign in buttons found")
                    return None
                await asyncio.sleep(5)

                # Step 4: Select B.C. driver's licence
                logging.info("Selecting B.C. driver's licence...")
                selects = await page.locator('text="Select"').all()
                visible = [s for s in selects if await s.is_visible()]
                if visible:
                    await visible[0].click()
                    await asyncio.sleep(2)

                # Step 5: Fill Step 1 fields (licence number and date of issue)
                logging.info("Filling driver's licence information...")
                inputs = await page.locator('input').all()

                date_parts = self.icbc.get('DateOfIssue', '').split('-')
                if len(date_parts) != 3:
                    logging.error("Invalid DateOfIssue format in config. Expected: YYYY-MMM-DD")
                    return None

                year, month, day = date_parts

                for inp in inputs:
                    inp_id = (await inp.get_attribute('id') or '').lower()
                    inp_name = (await inp.get_attribute('name') or '').lower()

                    try:
                        if 'cardnum' in inp_id or 'cardnum' in inp_name:
                            await inp.evaluate(f'el => el.value = "{self.icbc["licenceNumber"]}"')
                            await inp.dispatch_event('input')
                            await inp.dispatch_event('change')
                            logging.debug("Filled licence number")
                        elif 'year' in inp_id or 'year' in inp_name:
                            await inp.evaluate(f'el => el.value = "{year}"')
                            await inp.dispatch_event('input')
                            await inp.dispatch_event('change')
                            logging.debug(f"Filled year: {year}")
                        elif 'day' in inp_id or 'day' in inp_name:
                            await inp.evaluate(f'el => el.value = "{day}"')
                            await inp.dispatch_event('input')
                            await inp.dispatch_event('change')
                            logging.debug(f"Filled day: {day}")
                    except Exception as e:
                        logging.debug(f"Error filling field: {e}")

                # Select month
                month_select = page.locator('select').first
                if await month_select.count() > 0:
                    await month_select.select_option(label=month)
                    logging.debug(f"Selected month: {month}")

                await asyncio.sleep(1)

                # Step 6: Click Next
                logging.info("Proceeding to Step 2...")
                next_btn = page.get_by_role("button", name="Next")
                if await next_btn.count() > 0:
                    # Check if button is enabled before clicking
                    is_disabled = await next_btn.get_attribute("disabled")
                    if is_disabled:
                        logging.error(f"Next button is disabled - form validation may have failed")
                        # Take screenshot for debugging
                        await page.screenshot(path="log/debug_form_state.png")
                        logging.info("Screenshot saved to debug_form_state.png")
                        # Log input field values for debugging
                        inputs = await page.locator('input:visible').all()
                        for inp in inputs:
                            inp_id = await inp.get_attribute('id') or ''
                            inp_value = await inp.input_value()
                            logging.info(f"Input field '{inp_id}': '{inp_value}'")
                        return None
                    await next_btn.click()
                    await asyncio.sleep(5)
                else:
                    logging.error("Next button not found")
                    await page.screenshot(path="log/debug_next_button_not_found.png")
                    return None

                # Step 7: Check if we're on keyword entry page (new simplified flow)
                # or need to select verification method (old flow)
                logging.info("Checking page state after Step 1...")

                # Check if we're already on keyword entry page (Step 2 of 2)
                page_content = await page.content()
                if "Enter your ICBC keyword" in page_content or "Step 2 of 2" in page_content:
                    logging.info("Already on keyword entry page (simplified flow)")
                else:
                    # Old flow: need to select verification method
                    logging.info("Selecting keyword verification method (old flow)...")
                    selects2 = await page.locator('text="Select"').all()
                    visible2 = [s for s in selects2 if await s.is_visible()]
                    logging.info(f"Found {len(visible2)} visible 'Select' elements")

                    if len(visible2) >= 3:
                        await visible2[2].click()  # Third option is keyword
                        await asyncio.sleep(2)
                    elif len(visible2) > 0:
                        logging.warning(f"Only {len(visible2)} Select elements, trying last one")
                        await visible2[-1].click()
                        await asyncio.sleep(2)

                # Step 8: Fill keyword
                logging.info("Entering ICBC keyword...")
                keyword_inputs = await page.locator('input:visible').all()
                keyword_filled = False

                for inp in keyword_inputs:
                    inp_name = (await inp.get_attribute('name') or '').lower()
                    inp_id = (await inp.get_attribute('id') or '').lower()
                    inp_type = (await inp.get_attribute('type') or '').lower()
                    # Look for keyword field or text input field
                    if 'keyword' in inp_name or 'keyword' in inp_id or inp_type == 'text':
                        await inp.fill(self.icbc["keyword"])
                        keyword_filled = True
                        logging.info("Filled keyword field")
                        break

                if not keyword_filled:
                    logging.error("Keyword field not found")
                    await page.screenshot(path="log/debug_keyword_not_found.png")
                    return None

                await asyncio.sleep(1)

                # Step 9: Click Submit
                logging.info("Submitting login...")
                submit_btn = page.get_by_role("button", name="Submit")
                if await submit_btn.count() > 0:
                    await submit_btn.click()
                    await asyncio.sleep(5)
                else:
                    logging.error("Submit button not found")
                    return None

                # Check if login was successful
                current_url = page.url
                if 'driver' in current_url or 'booking' in current_url:
                    logging.info("✅ Login successful!")

                    # Wait a bit more for any pending requests
                    await asyncio.sleep(2)

                    if self.captured_token:
                        logging.info("✅ Authorization token captured successfully")
                        return self.captured_token
                    else:
                        logging.error("Login succeeded but no token was captured")
                        return None
                else:
                    logging.error(f"Login failed - unexpected URL: {current_url}")
                    return None

            except Exception as e:
                logging.error(f"Login error: {e}")
                import traceback
                traceback.print_exc()
                return None
            finally:
                await browser.close()


def get_weblogin_playwright(config, headless=True):
    """
    Drop-in replacement for the old get_weblogin() function
    Uses Playwright to perform KBA login and returns token in compatible format

    Args:
        config: Configuration dictionary
        headless: Whether to run browser in headless mode

    Returns:
        Mock response object with Authorization header, or None if failed
    """
    # Run async login
    login = PlaywrightLogin(config)
    token = asyncio.run(login.login_and_get_token(headless=headless))

    if token:
        # Return a mock response object that mimics requests.Response
        class MockResponse:
            def __init__(self, token, response_data, config):
                self.status_code = 200
                self.headers = {'Authorization': token}
                # Use captured response data if available, otherwise create minimal data
                if response_data:
                    self._json_data = response_data
                    # Ensure drvrId is in config for later use
                    if 'drvrId' in response_data:
                        config['icbc']['drvrID'] = response_data['drvrId']
                else:
                    self._json_data = {'drvrId': config.get('icbc', {}).get('drvrID', '')}

            def json(self):
                return self._json_data

        return MockResponse(token, login.captured_response_data, config)
    else:
        return None


# For testing
if __name__ == "__main__":
    import yaml

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    with open('config.yml', 'r') as f:
        config = yaml.safe_load(f)

    response = get_weblogin_playwright(config, headless=True)

    if response:
        token = response.headers.get('Authorization')
        print(f"\n✅ Success! Token: {token[:80]}...")
    else:
        print("\n❌ Login failed")
