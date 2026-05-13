import argparse
import random
#import pygame

import requests
import json
import yaml
from datetime import datetime, timedelta
from datetime import time as t
import os
import threading
import time
from faker import Faker
from twilio.rest import Client
from pypushdeer import PushDeer
import logging
import ctypes
import imaplib
import email
import re
from email.header import decode_header
from zoneinfo import ZoneInfo
from pathlib import Path
from playwright_login import get_weblogin_playwright
from token_manager import TokenManager

MB_OK = 0x0
MB_TOPMOST = 0x00040000


def safely_run(func):
    def inner_func(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logging.error("excute {}, got exception: {}".format(func.__name__, e))

    return inner_func


@safely_run
def send_ntfy(config, subject, body):
    if not config["ntfy"]["enable"]:
        return
    url = "https://ntfy.sh/{}".format(config["ntfy"]["topic"])
    requests.post(url, data=body, headers={"Title": subject})


@safely_run
def send_host_notify(config, subject, body):
    if not config["pushlocal"]["enable"]:
        return
    ret = os.system('XDG_RUNTIME_DIR=/run/user/$(id -u) /usr/bin/notify-send -i emblem-danger "{}"'.format(subject))
    logging.info("send local, success={}".format(ret))


@safely_run
def play_notification_sound(config, subject, body):
    if not config.get("pushsound", {}).get("enable", False):
        return
    
    audio_file = config.get("pushsound", {}).get("audio_file", "")
    
    # If no custom audio file specified, use system beep
    if not audio_file:
        try:
            # Try system beep first
            ret = os.system('beep -f 800 -l 500 -r 3 2>/dev/null')
            if ret != 0:
                # If beep command not available, try terminal bell
                print('\a' * 3)  # Terminal bell
                logging.info("played terminal bell notification")
            else:
                logging.info("played system beep notification")
        except Exception as e:
            logging.error("failed to play system sound: {}".format(e))
    else:
        # Play custom audio file
        try:
            # Check if file exists
            if not os.path.exists(audio_file):
                logging.error("audio file not found: {}".format(audio_file))
                # Fallback to terminal bell
                print('\a' * 3)
                return
            
            # Try system audio players first
            audio_commands = [
                'mpg123 -q "{}" 2>/dev/null'.format(audio_file),  # MP3 files
                'paplay "{}" 2>/dev/null'.format(audio_file),     # PulseAudio  
                'aplay "{}" 2>/dev/null'.format(audio_file),      # ALSA
                'ffplay -nodisp -autoexit "{}" 2>/dev/null'.format(audio_file),  # FFmpeg
            ]
            
            played = False
            for cmd in audio_commands:
                ret = os.system(cmd)
                if ret == 0:
                    played = True
                    logging.info("played audio file: {}".format(audio_file))
                    break
            
            # Try pygame as fallback (but with process timeout)
            if not played:
                try:
                    import subprocess
                    pygame_cmd = 'python3 -c "import pygame,time; pygame.mixer.init(); pygame.mixer.music.load(\'{}\'); pygame.mixer.music.play(); time.sleep(3); pygame.mixer.quit()" 2>/dev/null'.format(audio_file)
                    result = subprocess.run(pygame_cmd, shell=True, timeout=5, capture_output=True)
                    if result.returncode == 0:
                        played = True
                        logging.info("played audio file with pygame subprocess: {}".format(audio_file))
                except Exception as e:
                    logging.info("pygame subprocess failed: {}".format(e))
            
            if not played:
                logging.warning("no audio players available, using terminal bell")
                # Fallback to terminal bell
                print('\a' * 3)
                logging.info("played terminal bell as fallback")
                
        except Exception as e:
            logging.error("error playing custom audio: {}".format(e))
            # Final fallback to terminal bell
            print('\a' * 3)


@safely_run
def send_pushdeer(config, subject, body):
    if not config["pushdeer"]["enable"]:
        return
    key = config['pushdeer']['key']
    pushdeer = PushDeer(pushkey=key)
    ret = pushdeer.send_markdown(subject, desp=body)
    logging.info("send pushdeer, success={}".format(ret))


@safely_run
def send_sms(config, subject, body):
    if not config["pushsms"]["enable"]:
        return
    msg = subject + body
    account_sid = config['pushsms']['accountSid']
    auth_token = config['pushsms']['authToken']
    client = Client(account_sid, auth_token)
    client.http_client.logger.setLevel(logging.ERROR)

    message = client.messages.create(
        from_=config['pushsms']['fromNumber'],
        body=msg,
        to=config['pushsms']['toNumber']
    )
    logging.info("send twilio, id={}, error={}".format(message.sid, message.error_code))


# Load configuration from YAML file
def load_config(config_path):
    with open(config_path, 'r') as file:
        return yaml.safe_load(file)


# Get data directory path from config and ensure it exists
def get_data_directory(config):
    data_dir = config.get('data_directory', './data')
    data_path = Path(data_dir)
    data_path.mkdir(parents=True, exist_ok=True)
    return data_path


# Get full file path within data directory
def get_data_file_path(config, filename):
    data_dir = get_data_directory(config)
    return data_dir / filename


# Generate realistic browser headers
_cached_headers = None

def generate_headers():
    global _cached_headers
    
    if _cached_headers is not None:
        return _cached_headers.copy()

    fake = Faker()
    _cached_headers = {
        'Content-type': 'application/json',
        'User-Agent': fake.user_agent(),
        'Sec-Ch-Ua-Platform': fake.random_element(elements=["Windows", "macOS", "Linux"]),
        'Sec-Ch-Ua': f'"Chromium";v="{fake.random_int(min=70, max=100)}", "Google Chrome";v="{fake.random_int(min=70, max=100)}", "Not;A=Brand";v="99"',
        'Dnt': '1',
        'Referer': 'https://onlinebusiness.icbc.com/webdeas-ui/booking',
        'Sec-ch-ua-mobile': '?0',
    }
    
    # _cached_headers = {
    #     'sec-ch-ua-platform': '"Linux"',
    #     'Referer': 'https://onlinebusiness.icbc.com/webdeas-ui/booking',
    #     'sec-ch-ua': '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
    #     'sec-ch-ua-mobile': '?0',
    #     'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36',
    #     'Accept': 'application/json, text/plain, */*',
    #     'Content-Type': 'application/json'
    # }
    return _cached_headers.copy()


# Get the web login response
def get_weblogin(config):
    login_url = "https://onlinebusiness.icbc.com/deas-api/v1/webLogin/webLogin"
    headers = generate_headers()
    payload = {
        "drvrLastName": config['icbc']['drvrLastName'],
        "licenceNumber": config['icbc']['licenceNumber'],
        "keyword": config['icbc']['keyword']
    }

    try:
        response = requests.put(login_url, data=json.dumps(payload), headers=headers, timeout=30)

        if response.status_code == 200:
            # Extract drvrId from response and update config
            response_json = response.json()
            if 'drvrId' in response_json:
                config['icbc']['drvrID'] = response_json['drvrId']
                # logging.info(f"Updated drvrID from response: {response_json['drvrId']}")
            
            return response
        elif response.status_code in [520, 524, 403]:
            if response.status_code == 403:
                logging.warning("Access denied (403) - may be rate limited or blocked")
            else:
                logging.warning(f"ICBC server issue ({response.status_code}) - server may be down")
            return None
        else:
            logging.error(f"Failed to get response, response code: {response.status_code}")
            return None
    except requests.exceptions.Timeout:
        logging.error("Request timed out while getting response")
        return None
    except requests.exceptions.ConnectionError:
        logging.error("Connection error while getting response - check internet connection")
        return None
    except Exception as e:
        logging.error(f"Unexpected error getting response: {e}")
        return None


# Get available appointments
def get_appointments(config, token):
    appointment_url = "https://onlinebusiness.icbc.com/deas-api/v1/webd/getAvailableAppointments"
    headers = generate_headers()
    headers['Authorization'] = token

    payload = {
        "aPosID": config['icbc']['posID'],
        "examType": str(config['icbc']['examClass']) + "-R-1",
        "examDate": datetime.now().strftime("%Y-%m-%d"),
        "ignoreReserveTime": "false",
        "prfDaysOfWeek": config['icbc']['prfDaysOfWeek'],
        "prfPartsOfDay": config['icbc']['prfPartsOfDay'],
        "lastName": config['icbc']['drvrLastName'],
        "licenseNumber": config['icbc']['licenceNumber']
    }

    # logging.info(f"get_appointments headers: {headers}")
    # logging.info(f"get_appointments payload: {payload}")

    response = requests.post(appointment_url, data=json.dumps(payload), headers=headers)

    if response.status_code == 200:
        appointments = response.json()[:10]
        for appointment in appointments:
            # logging.debug(appointment)   
            date = appointment["appointmentDt"]["date"]
            day_of_week = appointment["appointmentDt"]["dayOfWeek"]
            time = appointment["startTm"]
            date_obj = datetime.strptime(date, "%Y-%m-%d")
            formatted_date = date_obj.strftime("%Y-%m-%d %A")
        return appointments
    logging.error("Authorization error or failed to get appointments, get status code: {}".format(response.status_code))
    return []


def save_time_to_file(config, filename, wait):
    file_path = get_data_file_path(config, filename)
    with open(file_path, 'w') as file:
        now = datetime.now()
        pause_time = now + timedelta(minutes=wait)
        file.write("{}\n".format(pause_time.strftime("%Y-%m-%d %H:%M:%S")))


def load_time_from_file(config, filename):
    file_path = get_data_file_path(config, filename)
    if file_path.exists():
        with open(file_path, 'r') as file:
            line = file.readline().strip()
            return (datetime.strptime(line, "%Y-%m-%d %H:%M:%S"), line)
    return (None, "")


def is_pause_time(config, filename):
    now = datetime.now()
    pause_time, pause_time_str = load_time_from_file(config, filename)
    if pause_time is not None:
        if now < pause_time:
            logging.info("It's not time[{}] to pause yet".format(pause_time_str))
            return True
    return False


# Save the appointments to a text file
def save_appointments_to_txt(config, appointments, filename):
    file_path = get_data_file_path(config, filename)
    with open(file_path, 'w') as file:
        for appointment in appointments:
            date = appointment["appointmentDt"]["date"]
            day_of_week = appointment["appointmentDt"]["dayOfWeek"]
            time = appointment["startTm"]
            date_obj = datetime.strptime(date, "%Y-%m-%d")
            formatted_date = date_obj.strftime("%Y-%m-%d %A")
            file.write(f"{formatted_date} {time}\n")


# Load the appointments from a text file
def load_appointments_from_txt(config, filename):
    appointments = []
    file_path = get_data_file_path(config, filename)
    if file_path.exists():
        with open(file_path, 'r') as file:
            for line in file:
                date_str, time = line.strip().rsplit(' ', 1)
                date_obj = datetime.strptime(date_str, "%Y-%m-%d %A")
                date = date_obj.strftime("%Y-%m-%d")
                day_of_week = date_obj.strftime("%A")
                appointments.append({
                    "appointmentDt": {"date": date, "dayOfWeek": day_of_week},
                    "startTm": time
                })
    return appointments


@safely_run
def parse_time_range(range_str):
    time_ranges = []
    for range_str in range_str.split(","):
        if len(range_str) > 0:
            start_str, end_str = range_str.split("-")
            start_time = datetime.strptime(start_str.strip(), "%H:%M").time()
            end_time = datetime.strptime(end_str.strip(), "%H:%M").time()
            time_ranges.append((start_time, end_time))
    return time_ranges


# Compare two lists of appointments and return if there are differences
@safely_run
def compare_appointments(old_appointments, new_appointments, config):
    old_set = set((appt["appointmentDt"]["date"], appt["startTm"]) for appt in old_appointments)
    new_set = set((appt["appointmentDt"]["date"], appt["startTm"]) for appt in new_appointments)
    newer = new_set - old_set
    # print(new_set)
    # print( old_set)
    # print(newer)
    time_ranges = parse_time_range(config['icbc']["expactTimeRange"])
    for ns in newer:
        date, _time = ns
        newdate = time.strptime(date, "%Y-%m-%d")
        tlow = time.strptime(config["icbc"]["expactAfterDate"], "%Y-%m-%d")
        tup = time.strptime(config["icbc"]["expactBeforeDate"], "%Y-%m-%d")

        print("newdate:", f"{newdate.tm_year}-{newdate.tm_mon:02d}-{newdate.tm_mday:02d}")
        if (tlow <= newdate) and (tup >= newdate):
            logging.info("get new appointment: {} {}".format(date, _time))
            tbook = datetime.strptime(_time.strip(), "%H:%M").time()
            for start, end in time_ranges:
                if start <= tbook <= end:
                    logging.info("get new eligible appointment: {} {}".format(date, _time))
                    return True
    return False


def format_appointments(appointments):
    formatted = "Latest 10 Appointments:\n"
    for appointment in appointments:
        date = appointment["appointmentDt"]["date"]
        day_of_week = appointment["appointmentDt"]["dayOfWeek"]
        time = appointment["startTm"]
        formatted += f"{date} ({day_of_week}) at {time}\n"
    return formatted


def is_special_time():
    now = datetime.now()
    start_time = t(23, 55)
    end_time = t(0, 5)
    if (start_time <= now.time() or now.time() < end_time):
        logging.info("skipped special time")
        return True
    return False


def notify_appointments(config, subject, body):
    threads = []
    notify_called_function = [send_host_notify, send_sms, send_pushdeer, send_ntfy, play_notification_sound]
    for f in notify_called_function:
        t = threading.Thread(target=f, args=(config, subject, body))
        threads.append(t)
        t.start()
    for t in threads:
        t.join()


# def playsound1():
# for _ in range(5):
#     winsound.PlaySound("SystemAsterisk", winsound.SND_ALIAS)
#     time.sleep(0.5)


def play_mp3(filepath):
    try:
        pygame.mixer.init()
        pygame.mixer.music.load(filepath)
        pygame.mixer.music.play(start=11.0)

        # Wait until the music is finished
        while pygame.mixer.music.get_busy():
            pygame.time.Clock().tick(10)
    except Exception as e:
        print(f"Error playing MP3: {e}")
    finally:
        pygame.mixer.quit()


# Example usage
# playmp3('C:/Users/YourName/Music/example.mp3')


# Global variable to store processed email IDs and cache
_processed_email_ids = set()
_email_cache = {}
_last_cache_update = None

# Global variable to store webAappointments for later use
_web_appointments = []

@safely_run
def save_processed_email_ids(config, email_ids, cache_file='processed_emails.txt'):
    """Save processed email IDs to file"""
    try:
        file_path = get_data_file_path(config, cache_file)
        with open(file_path, 'w') as f:
            for email_id in email_ids:
                f.write(f"{email_id}\n")
    except Exception as e:
        logging.warning(f"Failed to save processed email IDs: {e}")

@safely_run
def load_processed_email_ids(config, cache_file='processed_emails.txt'):
    """Load processed email IDs from file"""
    email_ids = set()
    try:
        file_path = get_data_file_path(config, cache_file)
        if file_path.exists():
            with open(file_path, 'r') as f:
                for line in f:
                    email_id = line.strip()
                    if email_id:
                        email_ids.add(email_id)
    except Exception as e:
        logging.warning(f"Failed to load processed email IDs: {e}")
    return email_ids

@safely_run
def check_idle_support(mail):
    """Check if server supports IDLE"""
    try:
        # Check server capabilities
        capabilities = mail.capabilities
        if b'IDLE' in capabilities:
            logging.info("Server supports IDLE")
            return True
        else:
            logging.info("Server does not support IDLE")
            return False
    except Exception as e:
        logging.warning(f"Could not check IDLE capability: {e}")
        return False

@safely_run
def wait_for_new_emails_idle(mail, timeout_seconds=60):
    """Use IDLE to wait for new emails - simplified implementation"""
    try:
        if not check_idle_support(mail):
            logging.info("IDLE not supported, falling back to regular polling")
            return False
        
        logging.info("Attempting to use IDLE...")
        
        # Try to use IDLE command manually
        tag = mail._new_tag()
        mail.send(f'{tag} IDLE\r\n'.encode())
        
        start_time = time.time()
        while time.time() - start_time < timeout_seconds:
            try:
                # Wait for server response
                response = mail.readline()
                if response:
                    response_str = response.decode('utf-8', errors='ignore')
                    logging.debug(f"IDLE response: {response_str.strip()}")
                    
                    # Check for EXISTS (new email) or EXPUNGE responses
                    if 'EXISTS' in response_str or 'RECENT' in response_str:
                        # Send DONE to exit IDLE
                        mail.send(b'DONE\r\n')
                        # Read the completion response
                        mail.readline()
                        logging.info("New email detected via IDLE")
                        return True
                        
                # Check timeout
                if time.time() - start_time >= timeout_seconds:
                    break
                    
            except Exception as e:
                logging.debug(f"IDLE read error: {e}")
                break
        
        # Send DONE to exit IDLE
        try:
            mail.send(b'DONE\r\n')
            mail.readline()  # Read completion response
        except:
            pass
            
        logging.info("IDLE timeout, no new emails detected")
        return False
        
    except Exception as e:
        logging.warning(f"IDLE failed: {e}")
        return False

@safely_run
def get_new_emails_multiple_strategies(mail, sender_email, timeout_minutes, subject="Verification code to book a road test"):
    """Try multiple search strategies to find emails with specific subject"""
    strategies = []
    
    # Strategy 1: SINCE with extended time range including subject
    extended_since = (datetime.now() - timedelta(minutes=timeout_minutes + 30)).strftime("%d-%b-%Y")
    # strategies.append(f'(FROM "{sender_email}" SUBJECT "{subject}" SINCE "{extended_since}")')
    
    # Strategy 2: Just sender and subject without date restriction 
    strategies.append(f'(FROM "{sender_email}" SUBJECT "{subject}")')
    
    # Strategy 3: Use SENTSINCE with subject
    #strategies.append(f'(FROM "{sender_email}" SUBJECT "{subject}" SENTSINCE "{extended_since}")')
    
    # Strategy 4: Recent emails from sender (will filter by subject later)
    #strategies.append(f'(FROM "{sender_email}" RECENT)')
    
    # Strategy 5: Only sender without subject (will filter manually)
    #strategies.append(f'(FROM "{sender_email}")')
    
    # Strategy 6: Only subject without sender (will filter manually)  
    #strategies.append(f'(SUBJECT "{subject}")')
    
    all_emails = set()
    
    for i, criteria in enumerate(strategies):
        try:
            logging.info(f"Trying search strategy {i+1}: {criteria}")
            status, messages = mail.search(None, criteria)
            
            if status == "OK" and messages[0]:
                email_ids = messages[0].split()
                logging.info(f"Strategy {i+1} found {len(email_ids)} emails")
                
                # For strategies without subject filter, manually check subject
                if "SUBJECT" not in criteria:
                    filtered_ids = []
                    for email_id in email_ids:
                        try:
                            status, msg_data = mail.fetch(email_id, "(ENVELOPE)")
                            if status == "OK":
                                envelope_data = msg_data[0][1].decode('utf-8', errors='ignore')
                                if subject.lower() in envelope_data.lower():
                                    filtered_ids.append(email_id)
                        except Exception as e:
                            logging.debug(f"Error checking subject for email {email_id}: {e}")
                            continue
                    
                    logging.info(f"Strategy {i+1} after subject filtering: {len(filtered_ids)} emails")
                    all_emails.update(filtered_ids)
                else:
                    all_emails.update(email_ids)
            else:
                logging.info(f"Strategy {i+1} found no emails")
                
        except Exception as e:
            logging.warning(f"Strategy {i+1} failed: {e}")
            continue
    
    # Convert back to list and sort by email ID (usually newer emails have higher IDs)
    result = sorted(list(all_emails), key=lambda x: int(x.decode() if isinstance(x, bytes) else x))
    logging.info(f"Combined strategies found {len(result)} total emails with subject '{subject}'")
    return result

@safely_run
def get_new_emails_from_cache(mail, search_criteria, cache_timeout_minutes=1, force_refresh=False, timeout_minutes=2, expected_subject="Verification code to book a road test"):
    """Get emails using cache mechanism with multiple search strategies"""
    global _email_cache, _last_cache_update
    
    current_time = datetime.now()
    cache_key = search_criteria
    
    # Check if cache is valid (unless force refresh is requested)
    if (not force_refresh and 
        _last_cache_update and 
        cache_key in _email_cache and 
        current_time - _last_cache_update < timedelta(minutes=cache_timeout_minutes)):
        logging.debug("Using cached email list")
        return _email_cache[cache_key]
    
    # Refresh cache using multiple strategies
    try:
        logging.info("Refreshing email cache with multiple search strategies...")
        
        # Force IMAP server to sync
        try:
            mail.check()  # Force server to update
            logging.info("Forced IMAP server sync")
        except:
            pass
            
        # Extract sender from search criteria
        sender_match = None
        if 'FROM "' in search_criteria:
            import re
            match = re.search(r'FROM "([^"]*)"', search_criteria)
            if match:
                sender_match = match.group(1)
        
        if sender_match:
            # Use multiple strategies with expected subject
            email_ids = get_new_emails_multiple_strategies(mail, sender_match, timeout_minutes, expected_subject)
            
            # If no emails found, try getting recent emails and filter by sender manually
            if not email_ids:
                logging.info("No emails found with search strategies, trying manual approach...")
                try:
                    # Get all recent emails (last 50)
                    status, messages = mail.search(None, 'ALL')
                    if status == "OK" and messages[0]:
                        all_email_ids = messages[0].split()
                        # Check the last 50 emails for the sender
                        recent_ids = all_email_ids[-50:] if len(all_email_ids) > 50 else all_email_ids
                        
                        for email_id in reversed(recent_ids):  # Start with newest
                            try:
                                status, msg_data = mail.fetch(email_id, "(ENVELOPE)")
                                if status == "OK":
                                    # Parse envelope to check sender and subject
                                    envelope_data = msg_data[0][1].decode('utf-8', errors='ignore')
                                    if (sender_match.lower() in envelope_data.lower() and 
                                        expected_subject.lower() in envelope_data.lower()):
                                        email_ids.append(email_id)
                                        logging.info(f"Found verification email from {sender_match}: {email_id}")
                                        if len(email_ids) >= 10:  # Limit to 10 recent emails
                                            break
                            except Exception as e:
                                logging.debug(f"Error checking email {email_id}: {e}")
                                continue
                                
                        logging.info(f"Manual search found {len(email_ids)} emails from {sender_match}")
                        
                except Exception as e:
                    logging.warning(f"Manual email search failed: {e}")
        else:
            # Fallback to original search
            status, messages = mail.search(None, search_criteria)
            if status == "OK" and messages[0]:
                email_ids = messages[0].split()
            else:
                email_ids = []
        
        old_count = len(_email_cache.get(cache_key, []))
        _email_cache[cache_key] = email_ids
        _last_cache_update = current_time
        logging.info(f"Updated email cache: {old_count} -> {len(email_ids)} emails")
        
        # Debug: show newest email IDs
        if email_ids:
            newest_ids = email_ids[-5:] if len(email_ids) >= 5 else email_ids
            logging.info(f"Newest email IDs: {[eid.decode() if isinstance(eid, bytes) else eid for eid in newest_ids]}")
        
        return email_ids
        
    except Exception as e:
        logging.error(f"Failed to update email cache: {e}")
        return _email_cache.get(cache_key, [])

@safely_run
def get_unprocessed_emails(email_ids, processed_ids):
    """Filter out already processed emails"""
    if not email_ids:
        return []
        
    if isinstance(email_ids[0], bytes):
        email_ids = [eid.decode() for eid in email_ids]
    
    unprocessed = [eid for eid in email_ids if eid not in processed_ids]
    logging.info(f"Found {len(unprocessed)} unprocessed emails out of {len(email_ids)} total")
    return unprocessed

@safely_run
def connect_gmail(config):
    if not config["gmail"]["enable"]:
        return None
    
    try:
        mail = imaplib.IMAP4_SSL(config["gmail"]["imap_server"], config["gmail"]["imap_port"])
        mail.login(config["gmail"]["email"], config["gmail"]["password"])
        logging.info("Gmail connection successful")
        return mail
    except Exception as e:
        logging.error(f"Failed to connect to Gmail: {e}")
        return None


@safely_run
def get_verification_code_from_gmail(config, timeout_minutes=None):
    global _processed_email_ids
    
    mail = connect_gmail(config)
    if not mail:
        return None
    
    # Get timeout and subject from config or use defaults
    if timeout_minutes is None:
        timeout_minutes = config.get("gmail", {}).get("verification_timeout_minutes", 2)
    
    expected_subject = config.get("gmail", {}).get("verification_email_subject", "Verification code to book a road test")
    
    # Load previously processed email IDs
    _processed_email_ids = load_processed_email_ids(config)
    
    try:
        mail.select("inbox")
        
        # Search for emails from roadtests-donotreply@icbc.com with specific subject within the timeout period
        since_date = (datetime.now() - timedelta(minutes=timeout_minutes)).strftime("%d-%b-%Y")
        search_criteria = f'(FROM "roadtests-donotreply@icbc.com" SUBJECT "{expected_subject}" SINCE "{since_date}")'
        
        start_time = time.time()
        timeout_seconds = timeout_minutes * 60
        check_interval = config.get("gmail", {}).get("check_interval_seconds", 10)
        use_idle = config.get("gmail", {}).get("use_idle", True)
        
        logging.info(f"Starting verification code search with {timeout_minutes} minute timeout")
        
        iteration = 0
        while time.time() - start_time < timeout_seconds:
            iteration += 1
            remaining_time = timeout_seconds - (time.time() - start_time)
            logging.info(f"=== Iteration {iteration}, {remaining_time:.1f}s remaining ===")
            
            # Force refresh cache every iteration to ensure we get new emails
            force_refresh = iteration > 1  # Don't force on first iteration to use any existing cache
            email_ids = get_new_emails_from_cache(mail, search_criteria, force_refresh=force_refresh, timeout_minutes=timeout_minutes, expected_subject=expected_subject)
            
            if email_ids:
                # Filter out already processed emails
                unprocessed_ids = get_unprocessed_emails(email_ids, _processed_email_ids)
                
                if unprocessed_ids:
                    logging.info(f"Processing {len(unprocessed_ids)} unprocessed emails...")
                    
                    # Process unprocessed emails (check all, not just the latest)
                    for email_id in reversed(unprocessed_ids):  # Start with newest
                        try:
                            # Mark as processed immediately to avoid reprocessing
                            email_id_str = email_id.decode() if isinstance(email_id, bytes) else email_id
                            _processed_email_ids.add(email_id_str)
                            
                            logging.info(f"Processing email ID: {email_id_str}")
                            
                            # Fetch the email
                            status, msg_data = mail.fetch(email_id, "(RFC822)")
                            
                            if status == "OK":
                                email_body = msg_data[0][1]
                                email_message = email.message_from_bytes(email_body)
                                
                                # Get email subject and sender for debugging
                                subject = email_message.get('Subject', 'No Subject')
                                sender = email_message.get('From', 'Unknown Sender')
                                logging.info(f"Email from: {sender}, Subject: {subject}")
                                
                                # Check if email is within the time limit
                                email_date = email_message.get('Date')
                                if email_date:
                                    try:
                                        email_time = email.utils.parsedate_to_datetime(email_date)
                                        # Convert to local timezone if needed
                                        if email_time.tzinfo is None:
                                            email_time = email_time.replace(tzinfo=datetime.now().astimezone().tzinfo)
                                        time_diff = datetime.now().astimezone() - email_time
                                        logging.info(f"Email timestamp: {email_time}, Age: {time_diff.total_seconds()/60:.1f} minutes")
                                        
                                        if time_diff.total_seconds() > timeout_minutes * 60:
                                            logging.info(f"Email {email_id_str} too old: {time_diff.total_seconds()/60:.1f} minutes")
                                            continue
                                    except Exception as e:
                                        logging.warning(f"Could not parse email date: {e}")
                                
                                # Extract verification code
                                verification_code = extract_verification_code(email_message)
                                if verification_code:
                                    logging.info(f"✅ Verification code found: {verification_code}")
                                    # Save processed IDs before returning
                                    save_processed_email_ids(config, _processed_email_ids)
                                    mail.logout()
                                    return verification_code
                                else:
                                    logging.info(f"❌ No verification code found in email {email_id_str}")
                                    
                        except Exception as e:
                            logging.error(f"Error processing email {email_id}: {e}")
                            continue
                else:
                    logging.info("All emails already processed")
            else:
                logging.info("No emails found matching criteria")
            
            # If no new emails or no verification code found, wait for new emails
            remaining_time = timeout_seconds - (time.time() - start_time)
            if remaining_time <= 0:
                logging.info("Timeout reached")
                break
                
            wait_time = min(check_interval, remaining_time)
            
            # Disable IDLE for now since it's unreliable, use regular polling
            # Try to use IDLE if supported and enabled
            if use_idle and wait_time >= 30 and False:  # Disabled for debugging
                logging.info("Using IDLE to wait for new emails...")
                if wait_for_new_emails_idle(mail, min(30, wait_time)):
                    # Force cache refresh on next iteration
                    logging.info("IDLE detected new email, refreshing...")
                    continue
            
            # Regular polling - always refresh cache on next iteration
            logging.info(f"⏰ Waiting {wait_time:.0f} seconds for new emails...")
            time.sleep(wait_time)
        
        logging.error("Timeout waiting for verification code email")
        # Save processed IDs before exiting
        save_processed_email_ids(config, _processed_email_ids)
        mail.logout()
        return None
        
    except Exception as e:
        logging.error(f"Error retrieving verification code: {e}")
        # Save processed IDs before exiting
        save_processed_email_ids(config, _processed_email_ids)
        if mail:
            mail.logout()
        return None


@safely_run
def extract_verification_code(email_message):
    """Extract verification code from email with improved error handling and content extraction"""
    content = ""
    all_content_parts = []
    
    try:
        if email_message.is_multipart():
            # Try to get content from all text parts (both plain and HTML)
            for part in email_message.walk():
                content_type = part.get_content_type()
                if content_type in ["text/plain", "text/html"]:
                    try:
                        # Try different encodings
                        payload = part.get_payload(decode=True)
                        if payload:
                            # Try UTF-8 first, then fallback to other encodings
                            for encoding in ['utf-8', 'latin1', 'cp1252', 'iso-8859-1']:
                                try:
                                    decoded_content = payload.decode(encoding)
                                    all_content_parts.append(f"[{content_type}]: {decoded_content}")
                                    if content_type == "text/plain" and not content:
                                        content = decoded_content
                                    break
                                except UnicodeDecodeError:
                                    continue
                            else:
                                # If all encodings fail, use errors='ignore'
                                decoded_content = payload.decode('utf-8', errors='ignore')
                                all_content_parts.append(f"[{content_type}-fallback]: {decoded_content}")
                                if content_type == "text/plain" and not content:
                                    content = decoded_content
                    except Exception as e:
                        logging.warning(f"Error decoding email part {content_type}: {e}")
                        continue
        else:
            # Single part email
            try:
                payload = email_message.get_payload(decode=True)
                if payload:
                    # Try different encodings
                    for encoding in ['utf-8', 'latin1', 'cp1252', 'iso-8859-1']:
                        try:
                            content = payload.decode(encoding)
                            break
                        except UnicodeDecodeError:
                            continue
                    else:
                        # If all encodings fail, use errors='ignore'
                        content = payload.decode('utf-8', errors='ignore')
            except Exception as e:
                logging.error(f"Error decoding single-part email: {e}")
                return None
        
        # If no plain text content, try to use HTML content
        if not content and all_content_parts:
            # Find HTML content and strip basic HTML tags
            for part_content in all_content_parts:
                if "[text/html]" in part_content:
                    html_content = part_content.replace("[text/html]: ", "")
                    # Basic HTML tag removal (simple approach)
                    content = re.sub(r'<[^>]+>', ' ', html_content)
                    logging.info("Using HTML content as fallback (HTML tags stripped)")
                    break
        
        if not content:
            logging.error("No readable content found in email")
            logging.debug(f"Available content parts: {[part[:100] + '...' for part in all_content_parts]}")
            return None
        
        # Log full content for debugging (truncated for readability)
        logging.debug(f"Email content (first 1000 chars): {content[:1000]}...")
        if len(content) > 1000:
            logging.debug(f"Email content (last 500 chars): ...{content[-500:]}")
        
        # Search for 6-digit verification codes with multiple patterns
        patterns = [
            r'\b(\d{6})\b',                    # Basic 6 digits with word boundaries
            r'(?:code|verification|pin).*?(\d{6})',  # "code: 123456" or similar
            r'(\d{6}).*?(?:code|verification|pin)',  # "123456 is your code" or similar
            r'[^0-9](\d{6})[^0-9]',           # 6 digits surrounded by non-digits
            r'(\d{3}[-\s]?\d{3})',            # 123-456 or 123 456 format
        ]
        
        all_matches = []
        for i, pattern in enumerate(patterns):
            matches = re.findall(pattern, content, re.IGNORECASE)
            if matches:
                # Clean matches (remove spaces/dashes for pattern 5)
                clean_matches = [re.sub(r'[-\s]', '', match) for match in matches]
                # Filter to only 6-digit codes
                valid_matches = [match for match in clean_matches if len(match) == 6 and match.isdigit()]
                if valid_matches:
                    all_matches.extend(valid_matches)
                    logging.info(f"Pattern {i+1} found matches: {valid_matches}")
        
        if all_matches:
            # Return the last match found (most likely the verification code)
            verification_code = all_matches[-1]
            logging.info(f"✅ Found 6-digit verification code: {verification_code}")
            return verification_code
        
        # Additional debugging: look for any digit sequences
        all_digits = re.findall(r'\d+', content)
        digit_lengths = [len(d) for d in all_digits]
        logging.warning(f"No 6-digit verification code found. Found digit sequences of lengths: {set(digit_lengths)}")
        logging.warning(f"All digit sequences: {all_digits[:10]}...")  # Show first 10
        
        return None
        
    except Exception as e:
        logging.error(f"Unexpected error in extract_verification_code: {e}")
        return None


@safely_run
def check_existing_appointments(weblogin_response_data):
    """
    Check existing appointments from get_weblogin response data.
    
    Args:
        weblogin_response_data: The response.json() content from get_weblogin function
        
    Returns:
        list: List of existing appointments, empty list if none found
    """
    global _web_appointments
    
    try:
        # Extract webAappointments from the response data
        web_appointments = weblogin_response_data.get('webAappointments', [])

        if web_appointments:
            # Store webAappointments in global variable for later use
            _web_appointments = web_appointments
            logging.info(f"✅ Found {len(web_appointments)} existing appointment(s)")
            return web_appointments
        else:
            # Clear global variable if no appointments
            _web_appointments = []
            logging.info("No existing appointments found")
            return []
            
    except Exception as e:
        logging.error(f"Error checking existing appointments from weblogin response: {e}")
        _web_appointments = []
        return []


@safely_run
def put_lock(config, token, appointment):
    lock_url = "https://onlinebusiness.icbc.com/deas-api/v1/webd/lock"
    headers = generate_headers()
    headers['Authorization'] = token
    
    payload = {
        "appointmentDt": {
            "date": appointment["appointmentDt"]["date"],
            "dayOfWeek": appointment["appointmentDt"]["dayOfWeek"]
        },
        "dlExam": {
            "code": str(config['icbc']['examClass']) + "-R-1",
            "description": str(config['icbc']['examClass']) + "-R-ROAD"
        },
        "drvrDriver": {
            "drvrId": config['icbc']['drvrID']
        },
        "drscDrvSchl": {},
        "instructorDlNum": None,
        "bookedTs": datetime.now(ZoneInfo("America/Vancouver")).strftime("%Y-%m-%dT%H:%M:%S"),
        "startTm": appointment["startTm"],
        "endTm": appointment.get("endTm", "16:10"),
        "posId": int(config['icbc']['posID']),
        "resourceId": appointment.get("resourceId", 19787),
        "signature": appointment.get("signature", "eyJhbGciOiJIUzI1NiJ9.eyJkbEV4YW0iOiI1LVItUk9BRCIsInN0YXJ0VG0iOiIxNTozNSIsInBvc0lkIjoyNzUsInN1YiI6IjMwNDcyOTA5IiwicmVzb3VyY2VJZCI6MTk3ODcsImFwcG9pbnRtZW50RHQiOiIyMDI1LTEyLTE5IiwiZW5kVG0iOiIxNjoxMCIsImV4cCI6MTc1NTEzMjg1NCwiaWF0IjoxNzU1MTMxMDU0fQ.IB_wz5OWRBGi3qbyD7xgaj7wo4fB7mem8W2vgvHyia0")
    }

#    payload = {
#        "appointmentDt": {},
#        "dlExam": {},
#        "drvrDriver": {
#            "drvrId": 2169682
#        },
#        "drscDrvSchl": {}
#    }
    
    logging.debug(f"Lock request headers: {headers}")
    logging.debug(f"Putting lock request: {payload}")
    
    try:
        # 转成原始 JSON 字符串（紧凑模式，避免空格和换行）
        raw_json = json.dumps(payload, separators=(',', ':'))
        response = requests.put(lock_url, data=raw_json, headers=headers)
        #response = requests.post(lock_url, data=json.dumps(payload), headers=headers)
        logging.info(f"Lock request response: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            logging.debug(f"Lock request result: {result}")
            return result
        else:
            logging.error(f"Lock request failed: {response.status_code}, {response.text}")
            return None
            
    except Exception as e:
        logging.error(f"Error submitting lock request: {e}")
        return None


@safely_run
def post_msg(config, token, appointment):
    msg_url = "https://onlinebusiness.icbc.com/deas-api/v1/webd/msgs"
    headers = generate_headers()
    headers['Authorization'] = token
    
    payload = {
        "aPosID": int(config['icbc']['posID']),
        "lemgMsgID": 35,
        "appointmentDt": appointment["appointmentDt"]["date"]
    }
    
    logging.info(f"Posting message request: {payload}")
    
    try:
        response = requests.post(msg_url, data=json.dumps(payload), headers=headers)
        logging.info(f"Message request response: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            logging.debug(f"Message request result: {result}")
            return result
        else:
            logging.error(f"Message request failed: {response.status_code}, {response.text}")
            return None
            
    except Exception as e:
        logging.error(f"Error submitting message request: {e}")
        return None


@safely_run
def submit_booking_request(config, token, appointment):
    # booking_url = "https://onlinebusiness.icbc.com/deas-api/v1/webd/sendOTP"
    booking_url = "https://onlinebusiness.icbc.com/deas-api/v1/webd/sendOTP"
    headers = generate_headers()
    headers['Authorization'] = token
    
    payload = {
        "bookedTs": datetime.now(ZoneInfo("America/Vancouver")).strftime("%Y-%m-%dT%H:%M:%S"),
        "drvrID": config['icbc']['drvrID'],
        "method": "E"
    }

    logging.info(f"Submitting booking request: {payload}")
    
    try:
        raw_json = json.dumps(payload, separators=(',', ':'))
        response = requests.post(booking_url, data=raw_json, headers=headers)
        # response = requests.post(booking_url, data=json.dumps(payload), headers=headers)
        logging.info(f"Booking request response: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            logging.info(f"Booking request result: {result}")
            return result
        else:
            logging.error(f"Booking request failed: {response.status_code}, {response.text}")
            return None
            
    except Exception as e:
        logging.error(f"Error submitting booking request: {e}")
        return None


@safely_run
def verify_booking_with_code(config, token, verification_code):
    verify_url = "https://onlinebusiness.icbc.com/deas-api/v1/webd/verifyOTP"
    headers = generate_headers()
    headers['Authorization'] = token
    
    payload = {
        "bookedTs": datetime.now(ZoneInfo("America/Vancouver")).strftime("%Y-%m-%dT%H:%M:%S"),
        "drvrID": config['icbc']['drvrID'],
        "code": verification_code
    }
    
    try:
        raw_json = json.dumps(payload, separators=(',', ':'))
        response = requests.put(verify_url, data=raw_json, headers=headers)
        logging.info(f"Verification response: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            logging.info(f"Verification result: {result}")
            return result
        else:
            logging.error(f"Verification failed: {response.status_code}, {response.text}")
            return None
            
    except Exception as e:
        logging.error(f"Error verifying booking: {e}")
        return None


@safely_run
def confirm_booking(config, token, appointment):
    confirm_url = "https://onlinebusiness.icbc.com/deas-api/v1/webd/book"
    headers = generate_headers()
    headers['Authorization'] = token
    
    payload = {
        "userId": f"WEBD:{config['icbc']['drvrID']}",
        "appointment": {
            "appointmentDt": {
                "date": appointment["appointmentDt"]["date"],
                "dayOfWeek": appointment["appointmentDt"]["dayOfWeek"]
            },
            "endTm": appointment.get("endTm", "12:20"),
            "lemgMsgId": 0,
            "posId": config['icbc']['posID'],
            "resourceId": appointment.get("resourceId", 21882),
            "startTm": appointment["startTm"],
            "bookedIndicator": "ACTIVE",
            "bookedTs": datetime.now(ZoneInfo("America/Vancouver")).strftime("%Y-%m-%dT%H:%M:%S"),
            "drscDrvSchl": {},
            "drvrDriver": {
                "drvrId": config['icbc']['drvrID'],
                "lastName": config['icbc']['drvrLastName'],
                "firstName": config['icbc'].get('firstName', ''),
                "licenseNumber": config['icbc']['licenceNumber'],
                "phoneNum": config['icbc'].get('phoneNum', '')
            },
            "officeNum": config['icbc'].get('officeNum', 94258),
            "posName": config['icbc'].get('posName', 'BURNABY CLAIM CENTRE'),
            "statusCode": "BOOKED",
            "checkTm": "11:30",
            "dlExam": {
                "code": str(config['icbc']['examClass']) + "-R-1",
                "description": f"Class {config['icbc']['examClass']} (full licence) Road Test"
            },
            "posGeo": config['icbc'].get('posGeo', {})
        },
        "action": "BOOKED"
    }
    
    try:
        raw_json = json.dumps(payload, separators=(',', ':'))
        logging.info(f"Booking payload: {raw_json}")
        response = requests.put(confirm_url, data=raw_json, headers=headers)
        logging.info(f"Confirmation response: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            logging.info(f"Booking confirmed successfully: {result}")
            return result
        else:
            logging.error(f"Booking confirmation failed: {response.status_code}, {response.text}")
            return None
            
    except Exception as e:
        logging.error(f"Error confirming booking: {e}")
        return None


@safely_run
def confirm_rebooking(config, token, appointment, web_appointments):
    rebook_url = "https://onlinebusiness.icbc.com/deas-api/v1/webd/rebook"
    headers = generate_headers()
    headers['Authorization'] = token
    
    # Extract data from web_appointments if available
    first_appointment = web_appointments[0] if web_appointments else {}
    driver_data = first_appointment.get("drvrDriver", {})
    pos_geo = first_appointment.get("posGeo", {})
    dl_exam = first_appointment.get("dlExam", {})
    
    payload = {
        "userId": f"WEBD:{driver_data.get('drvrId', config['icbc']['drvrID'])}",
        "appointment": {
            "appointmentDt": {
                "date": first_appointment["appointmentDt"]["date"],
                "dayOfWeek": first_appointment["appointmentDt"]["dayOfWeek"]
            },
            "endTm": first_appointment.get("endTm", "16:20"),
            "lemgMsgId": first_appointment.get("lemgMsgId", 0),
            "posId": first_appointment.get("posId", config['icbc']['posID']),
            "resourceId": first_appointment.get("resourceId", 19748),
            "startTm": first_appointment.get("startTm"),
            "bookedIndicator": "ACTIVE",
            "bookedTs": first_appointment.get("bookedTs"),
            "drscDrvSchl": first_appointment.get("drscDrvSchl", {}),
            "drvrDriver": {
                "drvrId": driver_data.get("drvrId", config['icbc']['drvrID']),
                "lastName": driver_data.get("lastName", config['icbc']['drvrLastName']),
                "firstName": driver_data.get("firstName", config['icbc'].get('firstName', '')),
                "licenseNumber": driver_data.get("licenseNumber", config['icbc']['licenceNumber']),
                "phoneNum": driver_data.get('phoneNum', '')
            },
            "officeNum": first_appointment.get("officeNum", config['icbc'].get('officeNum', 92642)),
            "posName": first_appointment.get("posName", config['icbc'].get('posName', 'NORTH VANCOUVER')),
            "statusCode": "BOOKED",
            "checkTm": first_appointment.get("checkTm", appointment.get("checkTm", "15:30")),
            "dlExam": {
                "code": dl_exam.get("code", str(config['icbc']['examClass']) + "-R-1"),
                "description": dl_exam.get("description", f"Class {config['icbc']['examClass']} (full licence) Road Test")
            },
            "posGeo": pos_geo if pos_geo else config['icbc'].get('posGeo', {})
        },
        # "appointment": {
        #     "appointmentDt": {
        #         "date": appointment["appointmentDt"]["date"],
        #         "dayOfWeek": appointment["appointmentDt"]["dayOfWeek"]
        #     },
        #     "endTm": appointment.get("endTm", "12:20"),
        #     "lemgMsgId": 0,
        #     "posId": config['icbc']['posID'],
        #     "resourceId": appointment.get("resourceId", 21882),
        #     "startTm": appointment["startTm"],
        #     "bookedIndicator": "ACTIVE",
        #     "bookedTs": datetime.now(ZoneInfo("America/Vancouver")).strftime("%Y-%m-%dT%H:%M:%S"),
        #     "drscDrvSchl": {},
        #     "drvrDriver": {
        #         "drvrId": config['icbc']['drvrID'],
        #         "lastName": config['icbc']['drvrLastName'],
        #         "firstName": driver_data.get("firstName", config['icbc'].get('firstName', '')),
        #         "licenseNumber": config['icbc']['licenceNumber'],
        #         "phoneNum": config['icbc'].get('phoneNum', '2498756331')
        #     },
        #     "officeNum": config['icbc'].get('officeNum', 94258),
        #     "posName": config['icbc'].get('posName', 'BURNABY CLAIM CENTRE'),
        #     "statusCode": "BOOKED",
        #     "checkTm": "11:30",
        #     "dlExam": {
        #         "code": str(config['icbc']['examClass']) + "-R-1",
        #         "description": f"Class {config['icbc']['examClass']} (full licence) Road Test"
        #     },
        #     "posGeo": pos_geo if pos_geo else config['icbc'].get('posGeo', {})
        # },
        "action": "RE-BOOKED"
    }
    
    try:
        raw_json = json.dumps(payload, separators=(',', ':'))
        logging.info(f"Rebooking payload: {raw_json}")
        response = requests.put(rebook_url, data=raw_json, headers=headers)
        logging.info(f"Rebooking response: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            logging.info(f"Rebooking confirmed successfully: {result}")
            return result
        else:
            logging.error(f"Rebooking confirmation failed: {response.status_code}, {response.text}")
            return None
            
    except Exception as e:
        logging.error(f"Error confirming rebooking: {e}")
        return None


@safely_run
def select_best_appointment(appointments, config):
    if not appointments:
        return None
    
    # Filter appointments based on date and time preferences
    valid_appointments = []
    time_ranges = parse_time_range(config['icbc']["expactTimeRange"])
    
    for appointment in appointments:
        date = appointment["appointmentDt"]["date"]
        time_str = appointment["startTm"]
        
        # Check date range
        date_obj = datetime.strptime(date, "%Y-%m-%d")
        after_date = datetime.strptime(config["icbc"]["expactAfterDate"], "%Y-%m-%d")
        before_date = datetime.strptime(config["icbc"]["expactBeforeDate"], "%Y-%m-%d")
        
        if after_date <= date_obj <= before_date:
            # Check time range
            appointment_time = datetime.strptime(time_str.strip(), "%H:%M").time()
            for start, end in time_ranges:
                if start <= appointment_time <= end:
                    valid_appointments.append(appointment)
                    break
    
    if not valid_appointments:
        return None
    
    # Select based on strategy
    strategy = config.get("autoBooking", {}).get("timeSelectionStrategy", "earliest")
    
    if strategy == "earliest":
        # Sort by date and time, return the earliest
        valid_appointments.sort(key=lambda x: (x["appointmentDt"]["date"], x["startTm"]))
        return valid_appointments[0]
    elif strategy == "best_time_slot":
        # Prefer appointments in the middle of preferred time ranges
        # For now, just return the first one
        return valid_appointments[0]
    else:
        return valid_appointments[0]


@safely_run
def attempt_booking(config, appointment, token):
    global _web_appointments
    
    max_retries = config.get("autoBooking", {}).get("maxRetryAttempts", 3)
    retry_interval = config.get("autoBooking", {}).get("retryIntervalSeconds", 30)
    
    for attempt in range(max_retries):
        logging.info(f"Booking attempt {attempt + 1}/{max_retries}")
        if not token:
            logging.error("Failed to get token for booking")
            continue
        
        # Put lock first
        lock_result = put_lock(config, token, appointment)
        if not lock_result:
            logging.error("Lock request failed")
            if attempt < max_retries - 1:
                time.sleep(retry_interval)
            continue
        
        # Post message
        msg_result = post_msg(config, token, appointment)
        if not msg_result:
            logging.error("Message request failed")
            if attempt < max_retries - 1:
                time.sleep(retry_interval)
            continue
        
        # Submit booking request
        booking_result = submit_booking_request(config, token, appointment)
        if not booking_result:
            logging.error("Booking request failed")
            if attempt < max_retries - 1:
                time.sleep(retry_interval)
            continue
        
        # Wait for and get verification code
        verification_code = get_verification_code_from_gmail(
            config, 
            config.get("autoBooking", {}).get("verificationCodeTimeoutMinutes", 10)
        )
        
        if not verification_code:
            logging.error("Failed to get verification code")
            if attempt < max_retries - 1:
                time.sleep(retry_interval)
            continue
        
        # Verify booking with code
        verify_result = verify_booking_with_code(config, token, verification_code)
        if not verify_result:
            logging.error("Verification failed")
            if attempt < max_retries - 1:
                time.sleep(retry_interval)
            continue
        
        # Check if web_appointments is empty to decide which confirmation function to call
        if not _web_appointments:
            logging.info("No existing appointments found, calling confirm_booking")
            confirm_result = confirm_booking(config, token, appointment)
        else:
            # logging.info(f"Found existing appointments: {_web_appointments}, calling confirm_rebooking")
            confirm_result = confirm_rebooking(config, token, appointment, _web_appointments)
        
        if confirm_result:
            logging.info("Booking confirmed successfully!")
            return True
        else:
            logging.error("Booking confirmation failed")
            if attempt < max_retries - 1:
                time.sleep(retry_interval)
    
    logging.error("All booking attempts failed")
    return False


@safely_run
def is_within_booking_time_window(config):
    booking_window = config.get("autoBooking", {}).get("bookingTimeWindow", "08:00-22:00")
    if not booking_window:
        return True
    
    try:
        start_str, end_str = booking_window.split("-")
        start_time = datetime.strptime(start_str.strip(), "%H:%M").time()
        end_time = datetime.strptime(end_str.strip(), "%H:%M").time()
        
        now = datetime.now().time()
        if start_time <= end_time:
            return start_time <= now <= end_time
        else:  # Time window crosses midnight
            return now >= start_time or now <= end_time
    except:
        logging.warning("Invalid booking time window format, assuming always allowed")
        return True


@safely_run
def save_booking_status(config, status, appointment_info=None):
    status_data = {
        "status": status,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "appointment": appointment_info
    }
    
    try:
        file_path = get_data_file_path(config, 'booking_status.json')
        with open(file_path, 'w') as f:
            json.dump(status_data, f, indent=2)
        logging.info(f"Booking status saved: {status}")
    except Exception as e:
        logging.error(f"Failed to save booking status: {e}")


@safely_run
def load_booking_status(config):
    try:
        file_path = get_data_file_path(config, 'booking_status.json')
        if file_path.exists():
            with open(file_path, 'r') as f:
                return json.load(f)
    except Exception as e:
        logging.error(f"Failed to load booking status: {e}")
    return None


@safely_run
def check_if_already_booked(config):
    status = load_booking_status(config)
    if status and status.get("status") == "booked":
        logging.info("Already have a successful booking, skipping...")
        return True
    return False

def job(config, token_manager=None):
    # Check if already successfully booked
    if check_if_already_booked(config):
        return "already_booked"

    # Check if auto booking is enabled
    auto_booking_enabled = config.get("autoBooking", {}).get("enable", False)

    # Check if within booking time window (if auto booking is enabled)
    if auto_booking_enabled and not is_within_booking_time_window(config):
        logging.info("Outside booking time window, skipping auto booking")
        auto_booking_enabled = False

    # Get authentication token (from cache if available, or login)
    if token_manager:
        response = token_manager.get_valid_token(headless=True)
    else:
        # Fallback to direct login if no token manager provided
        response = get_weblogin_playwright(config, headless=True)

    if not response:
        logging.error("No response received. Exiting.")
        return "token_failed"
    
    token = response.headers.get("Authorization", "")
    if not token:
        logging.error("No token received. Exiting.")
        return "token_failed"
    
    # Check for existing appointments from weblogin response (to avoid conflicts)
    weblogin_data = response.json()
    existing_appointments = check_existing_appointments(weblogin_data)
    #if existing_appointments:
    #    logging.info(f"Found existing appointments: {existing_appointments}")
    #    save_booking_status(config, "already_has_appointment", existing_appointments)
    #    if auto_booking_enabled and config.get("autoBooking", {}).get("exitAfterSuccess", True):
    #        return "existing_appointment"
    
    # Get available appointments
    new_appointments = get_appointments(config, token)
    if not new_appointments:
        logging.info("No appointments available")
        return "no_appointments"
    
    # Display available appointment dates
    date_set = set()
    for appointment in new_appointments:
        date_set.add(appointment["appointmentDt"]["date"])
    print(f"Available appointment dates: {date_set}")
    
    # Select best appointment based on preferences
    selected_appointment = select_best_appointment(new_appointments, config)
    
    if selected_appointment:
        appointment_info = {
            "date": selected_appointment["appointmentDt"]["date"],
            "time": selected_appointment["startTm"],
            "dayOfWeek": selected_appointment["appointmentDt"]["dayOfWeek"]
        }
        
        logging.info(f"Found suitable appointment: {appointment_info}")
        
        if auto_booking_enabled:
            # Attempt automatic booking
            logging.info("Starting automatic booking process...")
            booking_success = attempt_booking(config, selected_appointment, token)
            
            if booking_success:
                logging.info("✅ Automatic booking successful!")
                save_booking_status(config, "booked", appointment_info)
                
                # Send success notification
                subject = "ICBC Automatic Booking Success"
                body = f"Successfully booked appointment on {appointment_info['date']} ({appointment_info['dayOfWeek']}) at {appointment_info['time']}"
                notify_appointments(config, subject, body)
                
                if config.get("autoBooking", {}).get("exitAfterSuccess", True):
                    return "booking_success"
            else:
                logging.error("❌ Automatic booking failed")
                save_booking_status(config, "booking_failed", appointment_info)
                
                # Send failure notification as backup
                subject = "ICBC Automatic Booking Failed - Manual Action Required"
                body = f"Failed to automatically book appointment on {appointment_info['date']} ({appointment_info['dayOfWeek']}) at {appointment_info['time']}\nPlease book manually as soon as possible!"
                notify_appointments(config, subject, body)
        else:
            # Auto booking disabled, just send notification (original behavior)
            logging.info("Auto booking disabled, sending notification only")
            subject = "ICBC Available Appointment Found"
            body = format_appointments([selected_appointment])
            notify_appointments(config, subject, body)
            
            # Pause scanning for manual processing if not in auto booking mode
            pause_time = config.get("pauseTimeMin", 5)
            save_time_to_file(config, 'pause_manual.txt', pause_time)
            logging.info("Notification sent, pausing scan for {} minutes for manual processing".format(pause_time))
            return "notification_sent_paused"
    else:
        logging.info("No suitable appointments found matching criteria")
    
    return "completed"


def init_logging(config):
    # Check if logging file_path is configured, otherwise use data directory
    logging_config = config.get('logging', {})
    if 'file_path' in logging_config:
        log_file = logging_config['file_path']
    else:
        log_file = get_data_file_path(config, 'log_icbc_roadtest_checker.log')
    
    logging.basicConfig(filename=log_file, level=logging.INFO,
                        format='%(asctime)s - %(levelname)s - %(message)s')


@safely_run
def request_limit(config):
    if config["requestLimit"]["enable"]:
        now = datetime.now().time()
        period = config['requestLimit']["period"]
        interval = config['requestLimit']["interval"]
        time_ranges = parse_time_range(period)
        for start, end in time_ranges:
            if start <= now <= end:
                last_run_time, last_run_time_str = load_time_from_file(config, 'last_run.txt')
                if last_run_time is not None:
                    if now - last_run_time.time() <= timedelta(minutes=int(interval)):
                        logging.info("request limit reached, last run time: {}".format(last_run_time_str))
                        return True
    return False


@safely_run
def validate_configuration(config):
    """Validate configuration and provide helpful feedback"""
    issues = []
    warnings = []
    
    # Check basic ICBC configuration
    required_icbc_fields = ['drvrLastName', 'licenceNumber', 'keyword', 'posID', 'examClass']
    for field in required_icbc_fields:
        if not config.get('icbc', {}).get(field):
            issues.append(f"Missing ICBC configuration: {field}")
    
    # Check auto booking configuration
    if config.get("autoBooking", {}).get("enable", False):
        # Gmail must be enabled for auto booking
        if not config.get("gmail", {}).get("enable", False):
            issues.append("Auto booking requires Gmail to be enabled")
        
        # Gmail credentials must be provided
        gmail_config = config.get("gmail", {})
        if not gmail_config.get("email"):
            issues.append("Gmail email address is required for auto booking")
        if not gmail_config.get("password"):
            issues.append("Gmail password (app password) is required for auto booking")
        
        # Check if password looks like an app password (typically 16 chars)
        password = gmail_config.get("password", "")
        if password:
            clean_password = password.replace(" ", "")
            if len(clean_password) != 16:
                warnings.append(f"Gmail password has {len(clean_password)} characters. App passwords are typically 16 characters. If Gmail login fails, consider using an app password for better compatibility.")
    
    return issues, warnings


def main():
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description="ICBC Appointment Checker with Auto Booking")
    parser.add_argument('config', type=str, help='Path to the config file')
    args = parser.parse_args()

    # Load configuration
    config = load_config(args.config)
    
    # Initialize logging with config
    init_logging(config)
    
    # Validate configuration
    config_issues, config_warnings = validate_configuration(config)
    if config_issues:
        print("❌ Configuration Issues Found:")
        for issue in config_issues:
            print(f"  - {issue}")
        print("\n📖 Please check AUTO_BOOKING_GUIDE.md for setup instructions")
        logging.error(f"Configuration validation failed: {config_issues}")
        return
    
    if config_warnings:
        print("⚠️ Configuration Warnings:")
        for warning in config_warnings:
            print(f"  - {warning}")
        print()
    
    # Show current configuration status
    auto_booking = config.get("autoBooking", {}).get("enable", False)
    gmail_enabled = config.get("gmail", {}).get("enable", False)
    
    print("🚗 ICBC Road Test Checker Started")
    print(f"📧 Gmail Integration: {'✅ Enabled' if gmail_enabled else '❌ Disabled'}")
    print(f"🤖 Auto Booking: {'✅ Enabled' if auto_booking else '❌ Disabled (Notification Only)'}")
    
    if auto_booking:
        strategy = config.get("autoBooking", {}).get("timeSelectionStrategy", "earliest")
        window = config.get("autoBooking", {}).get("bookingTimeWindow", "08:00-22:00")
        print(f"⏰ Booking Window: {window}")
        print(f"🎯 Selection Strategy: {strategy}")
        print("⚠️  Program will EXIT after successful booking")
    
    consecutive_failures = 0
    max_consecutive_failures = 10

    # Initialize token manager for efficient token caching
    token_manager = TokenManager(config)
    logging.info("🔐 Token manager initialized (tokens will be cached for 4 minutes)")

    while True:
        # Check if in manual pause period
        if is_pause_time(config, 'pause_manual.txt'):
            logging.info("In manual pause period, waiting for user action...")
            time.sleep(30)
            continue
            
        if request_limit(config):
            logging.info("Request limit reached, sleep 10 seconds")
            time.sleep(10)
            continue
            
        job_result = job(config, token_manager)
        save_time_to_file(config, 'last_run.txt', 0)
        
        # Handle different job results
        if job_result == "booking_success":
            print("🎉 BOOKING SUCCESSFUL! Program will exit.")
            if config.get("autoBooking", {}).get("exitAfterSuccess", True):
                logging.info("Exiting program due to successful booking")
                break
                
        elif job_result in ["already_booked", "existing_appointment"]:
            print(f"ℹ️  {job_result.replace('_', ' ').title()}")
            if config.get("autoBooking", {}).get("exitAfterSuccess", True):
                logging.info(f"Exiting program due to: {job_result}")
                break
                
        elif job_result == "token_failed":
            consecutive_failures += 1
            print(f"❌ Failed to get authentication token (attempt {consecutive_failures}/{max_consecutive_failures})")
            if consecutive_failures >= max_consecutive_failures:
                print("🚨 Too many consecutive failures. ICBC service may be down. Exiting.")
                logging.error("Too many consecutive token failures, exiting")
                break
        elif job_result == "no_appointments":
            consecutive_failures = 0
            print("📅 No appointments available, continuing to monitor...")
        elif job_result == "notification_sent_paused":
            consecutive_failures = 0
            pause_time = config.get("pauseTimeMin", 5)
            print(f"🔊 Notification sent! Pausing scan for {pause_time} minutes for manual processing...")
            print("💡 Delete 'pause_manual.txt' file to resume scanning immediately")
        else:
            consecutive_failures = 0
            print(f"📊 Status: {job_result}")
        
        # Sleep between iterations (only if continuing)
        seconds = random.randint(10, 15)
        print(f"💤 Sleeping {seconds} seconds... (Ctrl+C to stop)")
        time.sleep(seconds)


if __name__ == "__main__":
    main()
