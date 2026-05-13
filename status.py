#!/usr/bin/env python3
"""
ICBC Auto Booking Status Checker
"""
import json
import os
from datetime import datetime
import yaml

def load_config(config_path):
    try:
        with open(config_path, 'r') as file:
            return yaml.safe_load(file)
    except:
        return None

def check_booking_status():
    """Check if there's a saved booking status"""
    try:
        if os.path.exists('booking_status.json'):
            with open('booking_status.json', 'r') as f:
                return json.load(f)
    except:
        pass
    return None

def check_last_run():
    """Check when the program last ran"""
    try:
        if os.path.exists('last_run.txt'):
            with open('last_run.txt', 'r') as f:
                line = f.readline().strip()
                return datetime.strptime(line, "%Y-%m-%d %H:%M:%S")
    except:
        pass
    return None

def check_log_summary():
    """Get a summary from recent logs"""
    try:
        with open('log_icbc_roadtest_checker.log', 'r') as f:
            lines = f.readlines()
            recent_lines = lines[-20:]  # Last 20 lines
            
            errors = sum(1 for line in recent_lines if 'ERROR' in line)
            warnings = sum(1 for line in recent_lines if 'WARNING' in line)
            no_appointments = sum(1 for line in recent_lines if 'No appointments available' in line)
            
            return {
                'total_recent_entries': len(recent_lines),
                'errors': errors,
                'warnings': warnings,
                'no_appointments': no_appointments
            }
    except:
        pass
    return None

def main():
    print("🔍 ICBC AUTO BOOKING SYSTEM STATUS")
    print("=" * 50)
    
    # Check configuration
    config = load_config('config.yml')
    if config:
        auto_booking = config.get("autoBooking", {}).get("enable", False)
        gmail_enabled = config.get("gmail", {}).get("enable", False)
        print(f"📧 Gmail Integration: {'✅ Enabled' if gmail_enabled else '❌ Disabled'}")
        print(f"🤖 Auto Booking: {'✅ Enabled' if auto_booking else '❌ Disabled'}")
        
        if auto_booking and gmail_enabled:
            strategy = config.get("autoBooking", {}).get("timeSelectionStrategy", "earliest")
            window = config.get("autoBooking", {}).get("bookingTimeWindow", "08:00-22:00")
            print(f"🎯 Selection Strategy: {strategy}")
            print(f"⏰ Booking Window: {window}")
    else:
        print("❌ Could not read configuration")
    
    print()
    
    # Check booking status
    booking_status = check_booking_status()
    if booking_status:
        status = booking_status.get('status', 'unknown')
        timestamp = booking_status.get('timestamp', 'unknown')
        appointment = booking_status.get('appointment')
        
        print(f"📊 Booking Status: {status}")
        print(f"⏰ Last Update: {timestamp}")
        
        if appointment:
            print(f"📅 Appointment Details: {appointment['date']} ({appointment['dayOfWeek']}) at {appointment['time']}")
        
        if status == 'booked':
            print("🎉 SUCCESS: Appointment has been booked!")
        elif status == 'booking_failed':
            print("⚠️  WARNING: Auto booking failed - manual action may be required")
    else:
        print("📊 Booking Status: No status saved (program hasn't run auto booking yet)")
    
    print()
    
    # Check last run time
    last_run = check_last_run()
    if last_run:
        time_diff = datetime.now() - last_run
        if time_diff.total_seconds() < 60:
            print(f"🟢 Program Status: Running (last activity {int(time_diff.total_seconds())} seconds ago)")
        elif time_diff.total_seconds() < 300:  # 5 minutes
            print(f"🟡 Program Status: Recently active ({int(time_diff.total_seconds()//60)} minutes ago)")
        else:
            print(f"🔴 Program Status: Not running (last activity {time_diff})")
    else:
        print("🔴 Program Status: Never run or no last run data")
    
    print()
    
    # Check log summary
    log_summary = check_log_summary()
    if log_summary:
        print("📋 Recent Activity Summary:")
        print(f"  • Total log entries: {log_summary['total_recent_entries']}")
        print(f"  • Errors: {log_summary['errors']}")
        print(f"  • Warnings: {log_summary['warnings']}")
        print(f"  • No appointments found: {log_summary['no_appointments']}")
        
        if log_summary['errors'] > 0:
            print("  ⚠️  Recent errors detected - check log file for details")
        elif log_summary['no_appointments'] > 0:
            print("  ✅ System is working - monitoring for appointments")
    else:
        print("📋 No log data available")
    
    print("\n" + "=" * 50)
    print("💡 Commands:")
    print("  • Run: python3 road.py config.yml")
    print("  • Test: python3 test_road.py config.yml")
    print("  • Logs: tail -f log_icbc_roadtest_checker.log")

if __name__ == "__main__":
    main()