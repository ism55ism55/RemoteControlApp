import os
import subprocess
import json
import hashlib
import time
import threading
from flask import Flask, request, jsonify, session
from flask_cors import CORS
import psutil
import secrets

app = Flask(__name__)
CORS(app)  # Enable cross-origin requests
app.secret_key = secrets.token_hex(16)  # For session management

# Configuration
CONFIG_FILE = 'config.json'
USERS_FILE = 'users.json'
SESSION_TIMEOUT = 1800  # 30 minutes

# In-memory storage for executable profiles and their statuses
exe_profiles = {}
users = {}
active_sessions = {}


# Load configuration from file
def load_config():
    global exe_profiles, users
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                exe_profiles = json.load(f)
        else:
            # Create default config if it doesn't exist
            exe_profiles = {}
            save_config()

        if os.path.exists(USERS_FILE):
            with open(USERS_FILE, 'r') as f:
                users = json.load(f)
        else:
            # Create a default admin user
            users = {
                "admin": {
                    "password": hashlib.sha256("admin123".encode()).hexdigest(),
                    "role": "admin"
                }
            }
            save_users()
    except Exception as e:
        print(f"Error loading configuration: {e}")


# Save configuration to file
def save_config():
    with open(CONFIG_FILE, 'w') as f:
        json.dump(exe_profiles, f, indent=4)


def save_users():
    with open(USERS_FILE, 'w') as f:
        json.dump(users, f, indent=4)


# Function to check if a process is running
def is_process_running(exe_path):
    exe_name = os.path.basename(exe_path)
    for proc in psutil.process_iter(['pid', 'name', 'exe']):
        try:
            # Check if the executable name matches
            if proc.info['name'].lower() == exe_name.lower():
                return True, proc.info['pid']
            # Also check the full path if available
            if 'exe' in proc.info and proc.info['exe'] and proc.info['exe'].lower() == exe_path.lower():
                return True, proc.info['pid']
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    return False, None


# Function to start an executable
def start_executable(exe_path, arguments=None):
    if not os.path.exists(exe_path):
        return False, "Executable not found"

    try:
        cmd = [exe_path]
        if arguments:
            cmd.extend(arguments.split())

        # Use subprocess.Popen to start the process without waiting
        subprocess.Popen(cmd, creationflags=subprocess.CREATE_NO_WINDOW)
        return True, "Process started"
    except Exception as e:
        return False, str(e)


# Function to stop an executable
def stop_executable(exe_path):
    running, pid = is_process_running(exe_path)
    if running and pid:
        try:
            process = psutil.Process(pid)
            process.terminate()
            # Wait for the process to terminate
            gone, alive = psutil.wait_procs([process], timeout=3)
            if alive:
                # Force kill if it doesn't terminate gracefully
                process.kill()
            return True, "Process stopped"
        except Exception as e:
            return False, str(e)
    return False, "Process not found"


# Function to check status of all executables
def update_all_statuses():
    for profile_id, profile in exe_profiles.items():
        running, pid = is_process_running(profile['path'])
        profile['status'] = 'running' if running else 'stopped'
        profile['pid'] = pid if running else None

        # Check if file exists
        if not os.path.exists(profile['path']):
            profile['status'] = 'unknown'


# Authentication middleware
def requires_auth(f):
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token or token not in active_sessions:
            return jsonify({"error": "Unauthorized"}), 401

        # Check if session has expired
        session_data = active_sessions[token]
        if time.time() - session_data['timestamp'] > SESSION_TIMEOUT:
            del active_sessions[token]
            return jsonify({"error": "Session expired"}), 401

        # Update session timestamp
        active_sessions[token]['timestamp'] = time.time()
        return f(*args, **kwargs)

    decorated.__name__ = f.__name__
    return decorated


# API Endpoints
@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return jsonify({"error": "Username and password required"}), 400

    # Check credentials
    if username in users and users[username]['password'] == hashlib.sha256(password.encode()).hexdigest():
        # Generate token
        token = secrets.token_hex(16)
        active_sessions[token] = {
            'username': username,
            'timestamp': time.time()
        }
        return jsonify({"token": token, "role": users[username]['role']}), 200
    else:
        return jsonify({"error": "Invalid credentials"}), 401


@app.route('/api/logout', methods=['POST'])
@requires_auth
def logout():
    token = request.headers.get('Authorization')
    if token in active_sessions:
        del active_sessions[token]
    return jsonify({"message": "Logged out successfully"}), 200


@app.route('/api/profiles', methods=['GET'])
@requires_auth
def get_profiles():
    update_all_statuses()  # Update all statuses before sending
    return jsonify(exe_profiles), 200


@app.route('/api/profiles', methods=['POST'])
@requires_auth
def add_profile():
    data = request.json
    required_fields = ['name', 'path']

    for field in required_fields:
        if field not in data:
            return jsonify({"error": f"Missing required field: {field}"}), 400

    profile_id = str(int(time.time()))  # Simple ID generation
    exe_profiles[profile_id] = {
        'name': data['name'],
        'path': data['path'],
        'arguments': data.get('arguments', ''),
        'status': 'unknown',
        'pid': None
    }

    # Check initial status
    running, pid = is_process_running(data['path'])
    exe_profiles[profile_id]['status'] = 'running' if running else 'stopped'
    exe_profiles[profile_id]['pid'] = pid if running else None

    # Check if file exists
    if not os.path.exists(data['path']):
        exe_profiles[profile_id]['status'] = 'unknown'

    save_config()
    return jsonify(exe_profiles[profile_id]), 201


@app.route('/api/profiles/<profile_id>', methods=['DELETE'])
@requires_auth
def delete_profile(profile_id):
    if profile_id not in exe_profiles:
        return jsonify({"error": "Profile not found"}), 404

    del exe_profiles[profile_id]
    save_config()
    return jsonify({"message": "Profile deleted"}), 200


@app.route('/api/profiles/<profile_id>/start', methods=['POST'])
@requires_auth
def start_profile(profile_id):
    if profile_id not in exe_profiles:
        return jsonify({"error": "Profile not found"}), 404

    profile = exe_profiles[profile_id]
    success, message = start_executable(profile['path'], profile['arguments'])

    if success:
        # Wait a moment for the process to start
        time.sleep(1)
        running, pid = is_process_running(profile['path'])
        profile['status'] = 'running' if running else 'stopped'
        profile['pid'] = pid if running else None
        save_config()
        return jsonify({"message": message, "status": profile['status']}), 200
    else:
        return jsonify({"error": message}), 400


@app.route('/api/profiles/<profile_id>/stop', methods=['POST'])
@requires_auth
def stop_profile(profile_id):
    if profile_id not in exe_profiles:
        return jsonify({"error": "Profile not found"}), 404

    profile = exe_profiles[profile_id]
    success, message = stop_executable(profile['path'])

    if success:
        profile['status'] = 'stopped'
        profile['pid'] = None
        save_config()
        return jsonify({"message": message, "status": profile['status']}), 200
    else:
        return jsonify({"error": message}), 400


@app.route('/api/profiles/<profile_id>/status', methods=['GET'])
@requires_auth
def get_profile_status(profile_id):
    if profile_id not in exe_profiles:
        return jsonify({"error": "Profile not found"}), 404

    profile = exe_profiles[profile_id]
    running, pid = is_process_running(profile['path'])
    profile['status'] = 'running' if running else 'stopped'
    profile['pid'] = pid if running else None

    # Check if file exists
    if not os.path.exists(profile['path']):
        profile['status'] = 'unknown'

    return jsonify({"status": profile['status'], "pid": profile['pid']}), 200


# Background thread to periodically update statuses
def status_updater():
    while True:
        update_all_statuses()
        save_config()
        time.sleep(30)  # Update every 30 seconds


if __name__ == '__main__':
    load_config()

    # Start the status updater thread
    updater_thread = threading.Thread(target=status_updater, daemon=True)
    updater_thread.start()

    # Run the server
    app.run(host='0.0.0.0', port=5000, debug=False)
