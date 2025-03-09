import json
import socket
import threading
import subprocess
import os
import time
from pathlib import Path

class RemoteControlServer:
    def __init__(self, host='0.0.0.0', port=5000, config_file='config.json'):
        self.host = host
        self.port = port
        self.config_file = config_file
        self.clients = {}  # {client_addr: auth_status}
        self.running_processes = {}  # {exe_name: process}
        self.load_config()
        
    def load_config(self):
        """Load configuration from config file."""
        try:
            with open(self.config_file, 'r') as f:
                self.config = json.load(f)
        except FileNotFoundError:
            # Create default config if not exists
            self.config = {
                "apps": [
                    {"name": "Notepad", "path": "C:\\Windows\\System32\\notepad.exe"},
                    {"name": "Calculator", "path": "C:\\Windows\\System32\\calc.exe"}
                ],
                "users": [
                    {"username": "admin", "password": "password123"}
                ]
            }
            self.save_config()
        
        # Initialize running_status for all apps
        for app in self.config["apps"]:
            app_name = app["name"]
            self.check_app_status(app_name)
            
    def save_config(self):
        """Save configuration to config file."""
        with open(self.config_file, 'w') as f:
            json.dump(self.config, f, indent=4)
            
    def check_app_status(self, app_name):
        """Check if an app is running and update its status."""
        for app in self.config["apps"]:
            if app["name"] == app_name:
                path = app["path"]
                
                # Check if the path exists
                if not os.path.exists(path):
                    return "yellow"  # Path doesn't exist
                
                # Check if process is in our tracked processes and running
                if app_name in self.running_processes:
                    if self.running_processes[app_name].poll() is None:
                        return "green"  # Running
                    else:
                        del self.running_processes[app_name]
                
                # Additional check by process name (simple version)
                exe_name = os.path.basename(path)
                try:
                    output = subprocess.check_output(f'tasklist /FI "IMAGENAME eq {exe_name}"', shell=True)
                    if exe_name.lower() in output.decode().lower():
                        return "green"  # Running
                except:
                    pass
                    
                return "red"  # Not running
        
        return "yellow"  # App not found in config
    
    def get_app_info(self):
        """Get all apps with their current status."""
        app_info = []
        for app in self.config["apps"]:
            status = self.check_app_status(app["name"])
            app_info.append({
                "name": app["name"],
                "path": app["path"],
                "status": status
            })
        return app_info
    
    def authenticate(self, username, password):
        """Authenticate a user."""
        for user in self.config["users"]:
            if user["username"] == username and user["password"] == password:
                return True
        return False
    
    def start_app(self, app_name):
        """Start a Windows application."""
        for app in self.config["apps"]:
            if app["name"] == app_name:
                path = app["path"]
                
                if not os.path.exists(path):
                    return {"status": "error", "message": f"Path not found: {path}"}
                
                try:
                    process = subprocess.Popen(path)
                    self.running_processes[app_name] = process
                    time.sleep(1)  # Give the process a moment to start
                    return {"status": "success", "message": f"Started {app_name}"}
                except Exception as e:
                    return {"status": "error", "message": str(e)}
        
        return {"status": "error", "message": f"App not found: {app_name}"}
    
    def stop_app(self, app_name):
        """Stop a Windows application."""
        for app in self.config["apps"]:
            if app["name"] == app_name:
                path = app["path"]
                exe_name = os.path.basename(path)
                
                # If we have the process in our tracking dict
                if app_name in self.running_processes:
                    try:
                        self.running_processes[app_name].terminate()
                        time.sleep(1)  # Give it a chance to terminate gracefully
                        if self.running_processes[app_name].poll() is None:
                            self.running_processes[app_name].kill()  # Force kill if not terminated
                        del self.running_processes[app_name]
                        return {"status": "success", "message": f"Stopped {app_name}"}
                    except Exception as e:
                        return {"status": "error", "message": str(e)}
                
                # Try to kill by name if not in our tracking dict
                try:
                    subprocess.call(f'taskkill /F /IM "{exe_name}"', shell=True)
                    return {"status": "success", "message": f"Stopped {app_name}"}
                except Exception as e:
                    return {"status": "error", "message": str(e)}
        
        return {"status": "error", "message": f"App not found: {app_name}"}
    
    def handle_client(self, client_socket, address):
        """Handle communication with a client."""
        self.clients[address] = False  # Not authenticated initially
        
        try:
            while True:
                # Receive data from the client
                data = client_socket.recv(1024)
                if not data:
                    break
                
                # Parse the received command
                try:
                    command = json.loads(data.decode('utf-8'))
                except json.JSONDecodeError:
                    response = {"status": "error", "message": "Invalid JSON format"}
                    client_socket.send(json.dumps(response).encode('utf-8'))
                    continue
                
                # Process commands
                if command["action"] == "authenticate":
                    if self.authenticate(command.get("username"), command.get("password")):
                        self.clients[address] = True  # Mark as authenticated
                        response = {"status": "success", "message": "Authentication successful"}
                    else:
                        response = {"status": "error", "message": "Authentication failed"}
                
                elif not self.clients[address]:
                    # Client not authenticated
                    response = {"status": "error", "message": "Authentication required"}
                
                elif command["action"] == "get_apps":
                    app_info = self.get_app_info()
                    response = {"status": "success", "apps": app_info}
                
                elif command["action"] == "start_app":
                    response = self.start_app(command.get("app_name"))
                
                elif command["action"] == "stop_app":
                    response = self.stop_app(command.get("app_name"))
                
                elif command["action"] == "app_status":
                    status = self.check_app_status(command.get("app_name"))
                    response = {"status": "success", "app_status": status}
                
                else:
                    response = {"status": "error", "message": "Unknown command"}
                
                # Send response back to the client
                client_socket.send(json.dumps(response).encode('utf-8'))
        
        except Exception as e:
            print(f"Error handling client {address}: {e}")
        finally:
            if address in self.clients:
                del self.clients[address]
            client_socket.close()
            print(f"Connection with {address} closed")
    
    def start(self):
        """Start the server."""
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        try:
            server_socket.bind((self.host, self.port))
            server_socket.listen(5)
            print(f"Server started on {self.host}:{self.port}")
            
            while True:
                client_socket, addr = server_socket.accept()
                print(f"Connection from {addr}")
                
                # Create a new thread to handle the client
                client_thread = threading.Thread(
                    target=self.handle_client, 
                    args=(client_socket, addr)
                )
                client_thread.daemon = True
                client_thread.start()
                
        except KeyboardInterrupt:
            print("Server is shutting down...")
        except Exception as e:
            print(f"Error: {e}")
        finally:
            server_socket.close()


if __name__ == "__main__":
    # Add option to configure host and port from command line
    import argparse
    parser = argparse.ArgumentParser(description="Remote Control Server for Windows applications")
    parser.add_argument('--host', default='0.0.0.0', help='Host IP to bind to')
    parser.add_argument('--port', type=int, default=5000, help='Port to bind to')
    parser.add_argument('--config', default='config.json', help='Path to config file')
    
    args = parser.parse_args()
    
    server = RemoteControlServer(host=args.host, port=args.port, config_file=args.config)
    server.start()
