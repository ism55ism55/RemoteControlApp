from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.image import Image
from kivy.uix.popup import Popup
from kivy.uix.filechooser import FileChooserListView
from kivy.clock import Clock
from kivy.graphics import Color, Rectangle
from kivy.core.window import Window
from kivy.uix.settings import SettingsWithSidebar
from kivy.config import ConfigParser

import socket
import json
import threading
import os
from functools import partial
import time

class ExeButton(BoxLayout):
    """Custom widget for executable buttons with LED status indicator."""
    def __init__(self, app_name, status="red", **kwargs):
        super(ExeButton, self).__init__(**kwargs)
        self.orientation = 'horizontal'
        self.size_hint_y = None
        self.height = 100
        self.padding = 10
        self.spacing = 10
        
        # LED status indicator
        self.status_frame = BoxLayout(size_hint=(0.2, 1))
        self.status_indicator = Image(source=self.get_led_image(status))
        self.status_frame.add_widget(self.status_indicator)
        
        # Button for app control
        self.control_button = Button(
            text=app_name,
            size_hint=(0.8, 1),
            font_size=20
        )
        
        self.add_widget(self.status_frame)
        self.add_widget(self.control_button)
    
    def get_led_image(self, status):
        """Return the appropriate LED image based on status."""
        # In a real app, you would use actual image files
        # Here we're using colors as placeholders
        status_images = {
            "red": "led_red.png",
            "green": "led_green.png",
            "yellow": "led_yellow.png"
        }
        
        # For demonstration, we'll return the status since we don't have the actual images
        # In a real app, you would return the path to the image file
        return status_images.get(status, "led_red.png")
    
    def update_status(self, status):
        """Update the LED status indicator."""
        self.status_indicator.source = self.get_led_image(status)


class RemoteControlClient(App):
    def __init__(self, **kwargs):
        super(RemoteControlClient, self).__init__(**kwargs)
        self.config = ConfigParser()
        self.config.read('remote_control.ini')
        
        # Set default settings if they don't exist
        if not self.config.has_section('Server'):
            self.config.add_section('Server')
            self.config.set('Server', 'host', '192.168.1.100')
            self.config.set('Server', 'port', '5000')
            self.config.write()
        
        if not self.config.has_section('App'):
            self.config.add_section('App')
            self.config.set('App', 'background_color', '#333333')
            self.config.set('App', 'background_image', '')
            self.config.write()
        
        # Connection variables
        self.host = self.config.get('Server', 'host')
        self.port = int(self.config.get('Server', 'port'))
        self.socket = None
        self.connected = False
        self.authenticated = False
        
        # App data
        self.apps = []
        self.app_widgets = {}
        
        # Background
        self.bg_color = self.config.get('App', 'background_color')
        self.bg_image = self.config.get('App', 'background_image')
    
    def build(self):
        # Create settings for the app
        self.settings_cls = SettingsWithSidebar
        
        # Main layout
        self.main_layout = BoxLayout(orientation='vertical', padding=10, spacing=10)
        
        # Add background color or image
        self.update_background()
        
        # Connection status at the top
        self.status_layout = BoxLayout(size_hint_y=0.1, padding=5)
        self.status_label = Label(text="Not Connected", size_hint_x=0.7)
        self.refresh_button = Button(
            text="Refresh Apps", 
            size_hint_x=0.3,
            disabled=True
        )
        self.refresh_button.bind(on_press=self.refresh_apps)
        
        self.status_layout.add_widget(self.status_label)
        self.status_layout.add_widget(self.refresh_button)
        
        # Authentication layout
        self.auth_layout = BoxLayout(orientation='vertical', size_hint_y=0.2, padding=5, spacing=5)
        
        self.auth_inputs = BoxLayout(spacing=5)
        self.username_input = TextInput(hint_text="Username", multiline=False, size_hint_x=0.4)
        self.password_input = TextInput(hint_text="Password", multiline=False, password=True, size_hint_x=0.4)
        self.login_button = Button(text="Login", size_hint_x=0.2)
        self.login_button.bind(on_press=self.authenticate)
        
        self.auth_inputs.add_widget(self.username_input)
        self.auth_inputs.add_widget(self.password_input)
        self.auth_inputs.add_widget(self.login_button)
        
        self.connect_layout = BoxLayout(spacing=5)
        self.connect_button = Button(text="Connect")
        self.connect_button.bind(on_press=self.connect_to_server)
        self.settings_button = Button(text="Server Settings")
        self.settings_button.bind(on_press=self.open_settings)
        
        self.connect_layout.add_widget(self.connect_button)
        self.connect_layout.add_widget(self.settings_button)
        
        self.auth_layout.add_widget(self.auth_inputs)
        self.auth_layout.add_widget(self.connect_layout)
        
        # App buttons layout (scrollable)
        self.apps_layout = GridLayout(cols=1, spacing=10, size_hint_y=0.7, padding=5)
        self.apps_layout.bind(minimum_height=self.apps_layout.setter('height'))
        
        # Add the layouts to the main layout
        self.main_layout.add_widget(self.status_layout)
        self.main_layout.add_widget(self.auth_layout)
        self.main_layout.add_widget(self.apps_layout)
        
        # Start periodic status updates if connected
        Clock.schedule_interval(self.update_app_statuses, 5)  # Every 5 seconds
        
        return self.main_layout
    
    def update_background(self):
        """Update the app background based on settings."""
        with self.main_layout.canvas.before:
            Color(*self.hex_to_rgb(self.bg_color))
            self.bg_rect = Rectangle(pos=self.main_layout.pos, size=self.main_layout.size)
        
        # Bind to size to update the background rectangle when the window resizes
        self.main_layout.bind(size=self._update_rect, pos=self._update_rect)
        
        # Add background image if set
        if self.bg_image and os.path.exists(self.bg_image):
            with self.main_layout.canvas.before:
                self.bg_image_rect = Rectangle(
                    pos=self.main_layout.pos,
                    size=self.main_layout.size,
                    source=self.bg_image
                )
    
    def _update_rect(self, instance, value):
        """Update the background rectangle when the window size changes."""
        self.bg_rect.pos = instance.pos
        self.bg_rect.size = instance.size
        
        if hasattr(self, 'bg_image_rect') and self.bg_image:
            self.bg_image_rect.pos = instance.pos
            self.bg_image_rect.size = instance.size
    
    def hex_to_rgb(self, hex_color):
        """Convert hex color string to RGB values (0-1 range for Kivy)."""
        hex_color = hex_color.lstrip('#')
        rgb = tuple(int(hex_color[i:i+2], 16)/255 for i in (0, 2, 4))
        return rgb + (1,)  # Add alpha channel
    
    def connect_to_server(self, instance):
        """Connect to the remote server."""
        try:
            self.host = self.config.get('Server', 'host')
            self.port = int(self.config.get('Server', 'port'))
            
            # Create a socket
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((self.host, self.port))
            
            self.connected = True
            self.status_label.text = f"Connected to {self.host}:{self.port}"
            self.connect_button.text = "Disconnect"
            self.connect_button.unbind(on_press=self.connect_to_server)
            self.connect_button.bind(on_press=self.disconnect_from_server)
            
            return True
        except Exception as e:
            self.status_label.text = f"Connection Error: {str(e)}"
            self.connected = False
            return False
    
    def disconnect_from_server(self, instance):
        """Disconnect from the server."""
        if self.socket:
            self.socket.close()
            self.socket = None
        
        self.connected = False
        self.authenticated = False
        self.status_label.text = "Disconnected"
        self.connect_button.text = "Connect"
        self.connect_button.unbind(on_press=self.disconnect_from_server)
        self.connect_button.bind(on_press=self.connect_to_server)
        self.refresh_button.disabled = True
        
        # Clear app buttons
        self.apps_layout.clear_widgets()
        self.app_widgets = {}
    
    def authenticate(self, instance):
        """Authenticate with the server."""
        if not self.connected:
            if not self.connect_to_server(None):
                return
        
        username = self.username_input.text
        password = self.password_input.text
        
        if not username or not password:
            self.status_label.text = "Please enter username and password"
            return
        
        try:
            # Send authentication request
            auth_request = {
                "action": "authenticate",
                "username": username,
                "password": password
            }
            
            self.send_command(auth_request)
            response = self.receive_response()
            
            if response.get("status") == "success":
                self.authenticated = True
                self.status_label.text = "Authenticated"
                self.login_button.text = "Logout"
                self.login_button.unbind(on_press=self.authenticate)
                self.login_button.bind(on_press=self.logout)
                self.refresh_button.disabled = False
                
                # Get apps after authentication
                self.refresh_apps(None)
            else:
                self.status_label.text = "Authentication Failed"
        except Exception as e:
            self.status_label.text = f"Authentication Error: {str(e)}"
    
    def logout(self, instance):
        """Log out from the server."""
        self.authenticated = False
        self.status_label.text = "Logged Out"
        self.login_button.text = "Login"
        self.login_button.unbind(on_press=self.logout)
        self.login_button.bind(on_press=self.authenticate)
        self.refresh_button.disabled = True
        
        # Clear app buttons
        self.apps_layout.clear_widgets()
        self.app_widgets = {}
    
    def refresh_apps(self, instance):
        """Get the list of applications from the server."""
        if not self.authenticated:
            return
        
        try:
            request = {"action": "get_apps"}
            self.send_command(request)
            response = self.receive_response()
            
            if response.get("status") == "success" and "apps" in response:
                self.apps = response["apps"]
                self.update_app_buttons()
                self.status_label.text = f"Loaded {len(self.apps)} applications"
            else:
                self.status_label.text = "Failed to get applications"
        except Exception as e:
            self.status_label.text = f"Error refreshing apps: {str(e)}"
    
    def update_app_buttons(self):
        """Update the app buttons in the UI."""
        self.apps_layout.clear_widgets()
        self.app_widgets = {}
        
        for app in self.apps:
            app_name = app["name"]
            status = app.get("status", "red")
            
            # Create button widget
            exe_button = ExeButton(app_name, status)
            exe_button.control_button.bind(
                on_press=partial(self.toggle_app, app_name)
            )
            
            self.apps_layout.add_widget(exe_button)
            self.app_widgets[app_name] = exe_button
    
    def toggle_app(self, app_name, instance):
        """Toggle app state (start/stop)."""
        if not self.authenticated:
            return
        
        # Get current status
        current_status = "red"
        for app in self.apps:
            if app["name"] == app_name:
                current_status = app.get("status", "red")
                break
        
        try:
            if current_status == "green":
                # App is running, stop it
                request = {"action": "stop_app", "app_name": app_name}
                self.send_command(request)
                response = self.receive_response()
                
                if response.get("status") == "success":
                    self.status_label.text = f"Stopped {app_name}"
                    # Update app status after stop command
                    self.request_app_status(app_name)
                else:
                    self.status_label.text = f"Failed to stop {app_name}: {response.get('message', '')}"
            else:
                # App is not running, start it
                request = {"action": "start_app", "app_name": app_name}
                self.send_command(request)
                response = self.receive_response()
                
                if response.get("status") == "success":
                    self.status_label.text = f"Started {app_name}"
                    # Update app status after start command
                    self.request_app_status(app_name)
                else:
                    self.status_label.text = f"Failed to start {app_name}: {response.get('message', '')}"
        except Exception as e:
            self.status_label.text = f"Error toggling app {app_name}: {str(e)}"
    
    def request_app_status(self, app_name):
        """Request the current status of an app."""
        if not self.authenticated:
            return
        
        try:
            request = {"action": "app_status", "app_name": app_name}
            self.send_command(request)
            response = self.receive_response()
            
            if response.get("status") == "success" and "app_status" in response:
                status = response["app_status"]
                # Update the app status in our apps list
                for app in self.apps:
                    if app["name"] == app_name:
                        app["status"] = status
                        break
                
                # Update the UI
                if app_name in self.app_widgets:
                    self.app_widgets[app_name].update_status(status)
        except Exception as e:
            print(f"Error getting app status: {str(e)}")
    
    def update_app_statuses(self, dt):
        """Periodically update app statuses."""
        if not self.authenticated or not self.connected:
            return
        
        try:
            request = {"action": "get_apps"}
            self.send_command(request)
            response = self.receive_response()
            
            if response.get("status") == "success" and "apps" in response:
                self.apps = response["apps"]
                
                # Update UI for each app
                for app in self.apps:
                    app_name = app["name"]
                    status = app.get("status", "red")
                    
                    if app_name in self.app_widgets:
                        self.app_widgets[app_name].update_status(status)
        except Exception as e:
            print(f"Error updating app statuses: {str(e)}")
    
    def send_command(self, command):
        """Send a command to the server."""
        if not self.socket:
            raise Exception("Not connected to server")
        
        data = json.dumps(command).encode('utf-8')
        self.socket.send(data)
    
    def receive_response(self):
        """Receive and parse response from the server."""
        if not self.socket:
            raise Exception("Not connected to server")
        
        data = self.socket.recv(4096)
        if not data:
            raise Exception("Connection closed by server")
        
        return json.loads(data.decode('utf-8'))
    
    def build_config(self, config):
        """Build the default configuration."""
        config.setdefaults('Server', {
            'host': '192.168.1.100',
            'port': '5000'
        })
        config.setdefaults('App', {
            'background_color': '#333333',
            'background_image': ''
        })
    
    def build_settings(self, settings):
        """Build the settings panel."""
        settings.add_json_panel('Server Settings', self.config, data=json.dumps([
            {'type': 'string', 'title': 'Host IP', 'section': 'Server', 'key': 'host'},
            {'type': 'numeric', 'title': 'Port', 'section': 'Server', 'key': 'port'},
            {'type': 'string', 'title': 'Background Color (HEX)', 'section': 'App', 'key': 'background_color'},
            {'type': 'path', 'title': 'Background Image', 'section': 'App', 'key': 'background_image'}
        ]))
    
    def on_config_change(self, config, section, key, value):
        """Handle configuration changes."""
        if section == 'Server':
            if key == 'host':
                self.host = value
            elif key == 'port':
                self.port = int(value)
        
        elif section == 'App':
            if key == 'background_color':
                self.bg_color = value
                self.update_background()
            elif key == 'background_image':
                self.bg_image = value
                self.update_background()


if __name__ == "__main__":
    RemoteControlClient().run()
