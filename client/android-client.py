from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.settings import SettingsWithSidebar
from kivy.clock import Clock
from kivy.graphics import Color, Ellipse, Rectangle
from kivy.utils import get_color_from_hex
from kivy.storage.jsonstore import JsonStore
import requests
import json
import os

# Configuration
CONFIG_FILE = 'remote_control_config.json'
DEFAULT_HOST = '192.168.1.100'
DEFAULT_PORT = '5000'


class StatusIndicator(BoxLayout):
    def __init__(self, **kwargs):
        super(StatusIndicator, self).__init__(**kwargs)
        self.size_hint = (None, None)
        self.size = (30, 30)
        self.status = 'unknown'

        with self.canvas:
            # Background
            Color(0.9, 0.9, 0.9, 1)
            self.bg = Ellipse(pos=self.pos, size=self.size)

            # Status light
            self.update_status(self.status)

        self.bind(pos=self.update_rect, size=self.update_rect)

    def update_rect(self, *args):
        self.bg.pos = self.pos
        self.bg.size = self.size
        self.status_light.pos = self.pos
        self.status_light.size = self.size

    def update_status(self, status):
        self.status = status
        with self.canvas:
            if status == 'running':
                Color(0, 1, 0, 1)  # Green
            elif status == 'stopped':
                Color(1, 0, 0, 1)  # Red
            else:
                Color(1, 1, 0, 1)  # Yellow

            self.status_light = Ellipse(pos=self.pos, size=self.size)


class ProfileButton(BoxLayout):
    def __init__(self, profile_id, profile_data, controller, **kwargs):
        super(ProfileButton, self).__init__(**kwargs)
        self.orientation = 'horizontal'
        self.size_hint_y = None
        self.height = 60
        self.profile_id = profile_id
        self.profile_data = profile_data
        self.controller = controller

        # Status indicator
        self.status_indicator = StatusIndicator()
        self.add_widget(self.status_indicator)

        # Info section
        info_layout = BoxLayout(orientation='vertical')
        self.name_label = Label(text=profile_data['name'], size_hint_y=0.7)
        status_text = f"Status: {profile_data['status'].capitalize()}"
        self.status_label = Label(text=status_text, size_hint_y=0.3)
        info_layout.add_widget(self.name_label)
        info_layout.add_widget(self.status_label)
        self.add_widget(info_layout)

        # Buttons
        self.start_button = Button(text='Start', size_hint_x=0.2)
        self.start_button.bind(on_release=self.start_exe)
        self.add_widget(self.start_button)

        self.stop_button = Button(text='Stop', size_hint_x=0.2)
        self.stop_button.bind(on_release=self.stop_exe)
        self.add_widget(self.stop_button)

        # Update status
        self.update_ui()

    def start_exe(self, instance):
        response = self.controller.start_profile(self.profile_id)
        if response and response.status_code == 200:
            data = response.json()
            self.profile_data['status'] = data['status']
            self.update_ui()

    def stop_exe(self, instance):
        response = self.controller.stop_profile(self.profile_id)
        if response and response.status_code == 200:
            data = response.json()
            self.profile_data['status'] = data['status']
            self.update_ui()

    def update_status(self, status):
        self.profile_data['status'] = status
        self.update_ui()

    def update_ui(self):
        self.status_indicator.update_status(self.profile_data['status'])
        status_text = f"Status: {self.profile_data['status'].capitalize()}"
        self.status_label.text = status_text

        # Update button states
        if self.profile_data['status'] == 'running':
            self.start_button.disabled = True
            self.stop_button.disabled = False
        elif self.profile_data['status'] == 'stopped':
            self.start_button.disabled = False
            self.stop_button.disabled = False
        else:  # unknown
            self.start_button.disabled = False
            self.stop_button.disabled = True


class ServerSettingsPopup(Popup):
    def __init__(self, app, **kwargs):
        super(ServerSettingsPopup, self).__init__(**kwargs)
        self.app = app
        self.title = 'Server Settings'
        self.size_hint = (0.8, 0.4)

        layout = BoxLayout(orientation='vertical', padding=10, spacing=10)

        # Host IP input
        host_layout = BoxLayout(size_hint_y=None, height=40)
        host_layout.add_widget(Label(text='Host IP:', size_hint_x=0.3))
        self.host_input = TextInput(text=self.app.host_ip, multiline=False, size_hint_x=0.7)
        host_layout.add_widget(self.host_input)
        layout.add_widget(host_layout)

        # Port input
        port_layout = BoxLayout(size_hint_y=None, height=40)
        port_layout.add_widget(Label(text='Port:', size_hint_x=0.3))
        self.port_input = TextInput(text=self.app.host_port, multiline=False, size_hint_x=0.7)
        port_layout.add_widget(self.port_input)
        layout.add_widget(port_layout)

        # Buttons
        buttons_layout = BoxLayout(size_hint_y=None, height=50, spacing=10)
        cancel_button = Button(text='Cancel')
        cancel_button.bind(on_release=self.dismiss)
        buttons_layout.add_widget(cancel_button)

        save_button = Button(text='Save')
        save_button.bind(on_release=self.save_settings)
        buttons_layout.add_widget(save_button)
        layout.add_widget(buttons_layout)

        # Status label
        self.status_label = Label(text='')
        layout.add_widget(self.status_label)

        self.content = layout

    def save_settings(self, instance):
        host_ip = self.host_input.text.strip()
        host_port = self.port_input.text.strip()

        if not host_ip:
            self.status_label.text = 'Host IP cannot be empty'
            return

        if not host_port.isdigit():
            self.status_label.text = 'Port must be a number'
            return

        self.app.host_ip = host_ip
        self.app.host_port = host_port
        self.app.update_server_url()
        self.app.save_config()
        self.status_label.text = 'Settings saved'
        Clock.schedule_once(lambda dt: self.dismiss(), 1)


class LoginScreen(BoxLayout):
    def __init__(self, app, **kwargs):
        super(LoginScreen, self).__init__(**kwargs)
        self.app = app
        self.orientation = 'vertical'
        self.padding = 20
        self.spacing = 10

        # Server info display
        server_display = BoxLayout(size_hint_y=None, height=40)
        server_label = Label(text=f'Server: {self.app.server_url}', size_hint_x=0.7)
        self.server_label = server_label
        server_display.add_widget(server_label)

        settings_button = Button(text='Settings', size_hint_x=0.3)
        settings_button.bind(on_release=self.show_settings)
        server_display.add_widget(settings_button)
        self.add_widget(server_display)

        # Username input
        username_layout = BoxLayout(size_hint_y=None, height=40)
        username_layout.add_widget(Label(text='Username:', size_hint_x=0.3))
        self.username_input = TextInput(multiline=False, size_hint_x=0.7)
        username_layout.add_widget(self.username_input)
        self.add_widget(username_layout)

        # Password input
        password_layout = BoxLayout(size_hint_y=None, height=40)
        password_layout.add_widget(Label(text='Password:', size_hint_x=0.3))
        self.password_input = TextInput(password=True, multiline=False, size_hint_x=0.7)
        password_layout.add_widget(self.password_input)
        self.add_widget(password_layout)

        # Login button
        self.login_button = Button(text='Login', size_hint_y=None, height=50)
        self.login_button.bind(on_release=self.login)
        self.add_widget(self.login_button)

        # Status label
        self.status_label = Label(text='')
        self.add_widget(self.status_label)

        # Fill remaining space
        self.add_widget(BoxLayout())

    def update_server_label(self):
        self.server_label.text = f'Server: {self.app.server_url}'

    def show_settings(self, instance):
        popup = ServerSettingsPopup(self.app)
        popup.bind(on_dismiss=lambda instance: self.update_server_label())
        popup.open()

    def login(self, instance):
        username = self.username_input.text
        password = self.password_input.text

        if not username or not password:
            self.status_label.text = 'Please enter username and password'
            return

        try:
            response = requests.post(f"{self.app.server_url}/api/login",
                                     json={"username": username, "password": password},
                                     timeout=5)

            if response.status_code == 200:
                data = response.json()
                self.app.auth_token = data['token']
                self.app.show_main_screen()
            else:
                self.status_label.text = 'Login failed: ' + response.json().get('error', 'Unknown error')
        except Exception as e:
            self.status_label.text = f'Connection error: {str(e)}'


class AddProfilePopup(Popup):
    def __init__(self, add_callback, **kwargs):
        super(AddProfilePopup, self).__init__(**kwargs)
        self.title = 'Add Executable Profile'
        self.size_hint = (0.8, 0.4)
        self.add_callback = add_callback

        layout = BoxLayout(orientation='vertical', padding=10, spacing=10)

        # Name input
        name_layout = BoxLayout(size_hint_y=None, height=40)
        name_layout.add_widget(Label(text='Name:', size_hint_x=0.3))
        self.name_input = TextInput(multiline=False, size_hint_x=0.7)
        name_layout.add_widget(self.name_input)
        layout.add_widget(name_layout)

        # Path input
        path_layout = BoxLayout(size_hint_y=None, height=40)
        path_layout.add_widget(Label(text='Path:', size_hint_x=0.3))
        self.path_input = TextInput(multiline=False, size_hint_x=0.7)
        path_layout.add_widget(self.path_input)
        layout.add_widget(path_layout)

        # Arguments input
        args_layout = BoxLayout(size_hint_y=None, height=40)
        args_layout.add_widget(Label(text='Arguments:', size_hint_x=0.3))
        self.args_input = TextInput(multiline=False, size_hint_x=0.7)
        args_layout.add_widget(self.args_input)
        layout.add_widget(args_layout)

        # Buttons
        buttons_layout = BoxLayout(size_hint_y=None, height=50, spacing=10)
        cancel_button = Button(text='Cancel')
        cancel_button.bind(on_release=self.dismiss)
        buttons_layout.add_widget(cancel_button)

        add_button = Button(text='Add')
        add_button.bind(on_release=self.add_profile)
        buttons_layout.add_widget(add_button)
        layout.add_widget(buttons_layout)

        self.content = layout

    def add_profile(self, instance):
        name = self.name_input.text
        path = self.path_input.text
        arguments = self.args_input.text

        if not name or not path:
            return

        profile_data = {
            'name': name,
            'path': path,
            'arguments': arguments
        }

        self.add_callback(profile_data)
        self.dismiss()


class MainScreen(BoxLayout):
    def __init__(self, app, **kwargs):
        super(MainScreen, self).__init__(**kwargs)
        self.app = app
        self.orientation = 'vertical'
        self.padding = 10
        self.spacing = 10

        # Top bar - first row
        top_info_bar = BoxLayout(size_hint_y=None, height=30)
        server_label = Label(text=f'Server: {self.app.server_url}', halign='left', size_hint_x=0.7)
        self.server_label = server_label
        top_info_bar.add_widget(server_label)

        settings_button = Button(text='Settings', size_hint_x=0.3)
        settings_button.bind(on_release=self.show_settings)
        top_info_bar.add_widget(settings_button)
        self.add_widget(top_info_bar)

        # Top bar - second row
        top_bar = BoxLayout(size_hint_y=None, height=50)
        self.title_label = Label(text='Remote Executable Control', size_hint_x=0.7)
        top_bar.add_widget(self.title_label)

        refresh_button = Button(text='Refresh', size_hint_x=0.15)
        refresh_button.bind(on_release=self.refresh_profiles)
        top_bar.add_widget(refresh_button)

        add_button = Button(text='Add', size_hint_x=0.15)
        add_button.bind(on_release=self.show_add_popup)
        top_bar.add_widget(add_button)

        logout_button = Button(text='Logout', size_hint_x=0.15)
        logout_button.bind(on_release=self.logout)
        top_bar.add_widget(logout_button)

        self.add_widget(top_bar)

        # Profiles area
        scroll_view = ScrollView()
        self.profiles_layout = GridLayout(cols=1, spacing=10, size_hint_y=None)
        self.profiles_layout.bind(minimum_height=self.profiles_layout.setter('height'))
        scroll_view.add_widget(self.profiles_layout)
        self.add_widget(scroll_view)

        # Status bar
        self.status_bar = Label(text='', size_hint_y=None, height=30)
        self.add_widget(self.status_bar)

        # Profile buttons (will be populated from server)
        self.profile_buttons = {}

        # Schedule periodic refresh
        Clock.schedule_interval(lambda dt: self.refresh_profiles(None), 10)

    def update_server_label(self):
        self.server_label.text = f'Server: {self.app.server_url}'

    def show_settings(self, instance):
        popup = ServerSettingsPopup(self.app)
        popup.bind(on_dismiss=lambda instance: self.update_server_label())
        popup.open()

    def refresh_profiles(self, instance):
        try:
            response = self.app.get_profiles()
            if response and response.status_code == 200:
                profiles = response.json()
                self.update_profiles(profiles)
                self.status_bar.text = 'Profiles refreshed'
            else:
                self.status_bar.text = 'Failed to refresh profiles'
        except Exception as e:
            self.status_bar.text = f'Error: {str(e)}'

    def update_profiles(self, profiles):
        # First update existing buttons
        for profile_id, profile_data in profiles.items():
            if profile_id in self.profile_buttons:
                self.profile_buttons[profile_id].update_status(profile_data['status'])
            else:
                # Create new button for new profile
                profile_button = ProfileButton(profile_id, profile_data, self.app)
                self.profile_buttons[profile_id] = profile_button
                self.profiles_layout.add_widget(profile_button)

        # Remove buttons for deleted profiles
        profiles_to_remove = []
        for profile_id in self.profile_buttons:
            if profile_id not in profiles:
                profiles_to_remove.append(profile_id)

        for profile_id in profiles_to_remove:
            self.profiles_layout.remove_widget(self.profile_buttons[profile_id])
            del self.profile_buttons[profile_id]

    def show_add_popup(self, instance):
        popup = AddProfilePopup(add_callback=self.add_profile)
        popup.open()

    def add_profile(self, profile_data):
        try:
            response = self.app.add_profile(profile_data)
            if response and response.status_code == 201:
                self.status_bar.text = 'Profile added'
                self.refresh_profiles(None)
            else:
                self.status_bar.text = 'Failed to add profile'
        except Exception as e:
            self.status_bar.text = f'Error: {str(e)}'

    def logout(self, instance):
        try:
            self.app.logout()
        except:
            pass
        self.app.show_login_screen()


class RemoteControlApp(App):
    def __init__(self, **kwargs):
        super(RemoteControlApp, self).__init__(**kwargs)
        self.title = 'Remote Executable Control'
        self.host_ip = DEFAULT_HOST
        self.host_port = DEFAULT_PORT
        self.server_url = f"http://{self.host_ip}:{self.host_port}"
        self.auth_token = None
        self.load_config()

    def build(self):
        self.root = BoxLayout()
        self.show_login_screen()
        return self.root

    def load_config(self):
        try:
            if os.path.exists(CONFIG_FILE):
                store = JsonStore(CONFIG_FILE)
                if 'host_ip' in store:
                    self.host_ip = store.get('host_ip')['value']
                if 'host_port' in store:
                    self.host_port = store.get('host_port')['value']
                self.update_server_url()
        except Exception as e:
            print(f"Error loading config: {e}")

    def update_server_url(self):
        self.server_url = f"http://{self.host_ip}:{self.host_port}"

    def save_config(self):
        try:
            store = JsonStore(CONFIG_FILE)
            store.put('host_ip', value=self.host_ip)
            store.put('host_port', value=self.host_port)
        except Exception as e:
            print(f"Error saving config: {e}")

    def show_login_screen(self):
        self.root.clear_widgets()
        self.login_screen = LoginScreen(self)
        self.root.add_widget(self.login_screen)

    def show_main_screen(self):
        self.root.clear_widgets()
        self.main_screen = MainScreen(self)
        self.root.add_widget(self.main_screen)
        self.main_screen.refresh_profiles(None)

    def get_profiles(self):
        if not self.auth_token:
            return None

        return requests.get(f"{self.server_url}/api/profiles",
                            headers={"Authorization": self.auth_token},
                            timeout=5)

    def add_profile(self, profile_data):
        if not self.auth_token:
            return None

        return requests.post(f"{self.server_url}/api/profiles",
                             json=profile_data,
                             headers={"Authorization": self.auth_token},
                             timeout=5)

    def start_profile(self, profile_id):
        if not self.auth_token:
            return None

        return requests.post(f"{self.server_url}/api/profiles/{profile_id}/start",
                             headers={"Authorization": self.auth_token},
                             timeout=5)

    def stop_profile(self, profile_id):
        if not self.auth_token:
            return None

        return requests.post(f"{self.server_url}/api/profiles/{profile_id}/stop",
                             headers={"Authorization": self.auth_token},
                             timeout=5)

    def logout(self):
        if not self.auth_token:
            return None

        response = requests.post(f"{self.server_url}/api/logout",
                                 headers={"Authorization": self.auth_token},
                                 timeout=5)
        self.auth_token = None
        return response


if __name__ == '__main__':
    RemoteControlApp().run()
