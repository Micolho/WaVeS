from pathlib import Path
from typing import Union

from PyQt5.QtWidgets import QMessageBox
from pycaw.pycaw import AudioUtilities
from serial.tools import list_ports
from sessions import SessionGroup, Master, Session, System
import webbrowser

default_mapping_txt = """
# Make sure this file is placed in the same directory as vc.exe. To make this startup on boot (for Windows), create a
# shortcut and place it in the Start-up folder.

# Application is either "master" for master volume, the application name "spotify.exe" (case insensitive) for Spotify
# (for Windows, this can be found in Task Manager under the "Details" tab), "unmapped" for any and all applications
# that are currently running, but have not been explicitly assigned a slider. "unmapped" excludes the master channel.
# Finally, "system" allows you to control the system sound volume.

# Stick to the syntax:
#<number>:<application>
# Here, number is the index
0: master
1: system
2: chrome.exe
3: spotify.exe
4: unmapped

# Find the device name when the sliders are connected to USB in Device Manager, so that when you switch USB ports,
# you don't have to change the COM port.
device name: Arduino Micro

# Indicate the number of sliders you're using:
sliders: 5
# Port is only used if the device name can't be found automatically.
port:COM8

# Make sure this matches the baudrate on the Arduino's Serial.begin() call.
baudrate:9600

# You can use this to invert the sliders: top is low volume, bottom is high volume.
inverted:False

# Set this to true if you want system sounds included in 'unmapped' if system sounds aren't assigned anywhere else.
system in unmapped:True
"""

class Control:
    """
    Contains all the fields necessary to control the audio sessions. It is responsible for parsing the config file,
    and harbours the sessions so that they can be accessed as needed.
    """

    def __init__(self, path=None):
        self.path = Path.cwd() / 'mapping.txt' if path is None else path

        if not self.path.is_file():
            self.path.parent.mkdir(exist_ok=True)
            self.path.touch()
            self.path.write_text(default_mapping_txt)
            QMessageBox.information(None, "New config file created", f"A new config file was created for you in the "
                                                                     f"same directory as the app:\n\n{str(self.path)}."
                                                                     f"\n\nIt will now be opened for you to view the "
                                                                     f"settings.")
            webbrowser.open(self.path)

        self.sessions = None
        self.port = None
        self.baudrate = None
        self.inverted = False
        self.unmapped = []
        self.found_pycaw_sessions = None

        self.load_config()  # Read the mappings from mapping.txt

        self.sliders = int(self.get_setting("sliders"))
        self.port = self.get_port()
        self.baudrate = self.get_setting("baudrate")
        self.inverted = self.get_setting("inverted") in ["True", "true"]

        self.get_mapping()

    def load_config(self):
        self.lines = self.path.read_text().split('\n')

    def get_setting(self, text):
        """
        Finds a line from the config file that contains "text".
        E.g. get_setting("0") will get the application that is set to the first slider, and get_setting("port")
        will get the port value from the config.
        :param text: Text that is to be found, like "port" or "baudrate"
        :return: The first element in the config file that contains "text", if any.
        """
        setting = list(filter(lambda x: text + ":" in x, self.lines))[0]
        return setting.split(":")[1].strip()

    def get_mapping(self):
        self.load_config()
        self.target_idxs = {}

        # For each of the sliders, get the mapping from config.txt, if it exists, and create the mapping.
        for idx in range(self.sliders):
            application_str = self.get_setting(str(idx))    # Get the settings from the config for each index.
            if ',' in application_str:
                application_str = tuple(app.strip() for app in application_str.split(','))
            self.target_idxs[application_str] = int(idx)    # Store the settings in a dictionary.

        session_dict = {}  # Look up table for the incoming Arduino data, mapping an index to a Session object.
        self.found_pycaw_sessions = AudioUtilities.GetAllSessions()

        active_sessions = {session.Process.name().lower(): session
                           for session in self.found_pycaw_sessions
                           if session.Process is not None}
        mapped_sessions = []
        system_session = [session for session in self.found_pycaw_sessions if 'SystemRoot' in session.DisplayName][0]

        for target, idx in self.target_idxs.items():
            if type(target) == str:
                target = target.lower()
                if target == 'master':
                    session_dict[idx] = Master(idx=idx)

                elif target == 'system':
                    session_dict[idx] = System(idx=idx, session=system_session)
                    mapped_sessions.append(system_session)

                elif target != 'unmapped':  # Can be any application
                    if target in active_sessions:
                        session = active_sessions.get(target, None)
                        if session is not None:
                            session_dict[idx] = Session(idx, session)
                        mapped_sessions.append(session)

            elif type(target) == tuple:
                active_sessions_in_group = []  # Track the sessions that are actually running and are mapped.

                for target_app in target:
                    target_app = target_app.lower()

                    # Exclude the other categories. Might change in the future.
                    if target_app in ['master', 'system', 'unmapped']:
                        continue

                    # Check if the target app is active.
                    session = active_sessions.get(target_app, None)
                    if session is not None:
                        active_sessions_in_group.append(session)
                        mapped_sessions.append(session)

                if len(active_sessions_in_group) > 0:
                    session_dict[idx] = SessionGroup(group_idx=idx, sessions=active_sessions_in_group)

                print(f"List found: {', '.join(target)}.")

        if 'unmapped' in self.target_idxs.keys():
            unmapped_idx = self.target_idxs['unmapped']
            unmapped_sessions = [ses for ses in active_sessions.values() if ses not in mapped_sessions]
            if self.get_setting('system in unmapped').lower() == 'false' and system_session in unmapped_sessions:
                unmapped_sessions.remove(system_session)

            session_dict[unmapped_idx] = SessionGroup(
                unmapped_idx,
                sessions=unmapped_sessions
            )

        self.sessions = session_dict

    def find_session(self, session_name: str, case_sensitive: bool = False) -> Union[Session, None]:
        """
        Finds a session with "session_name", if it exists. Can be searched for with case sensitivity if needed.
        :param session_name: Name of the Process object of the session, like "chrome.exe" or "Spotify.exe".
        Case insensitive by default.
        :param case_sensitive: Boolean flag to search for "session_name" with case sensitivity.
        :return: The Session with name "session_name" if it exists, None otherwise.
        """
        for idx, session in self.sessions.items():
            if not case_sensitive:
                if session.name.lower() == session_name.lower():
                    return session
            else:
                if session.name == session_name:
                    return session
        else:
            return None

    def get_sessions(self) -> list:
        """
        Returns all the currently mapped audio sessions.
        :return: List of all sessions that are currently mapped.
        """
        return list(self.sessions.values())

    def set_volume(self, values: list):
        for index, app in self.sessions.items():
            volume = values[index] / 1023
            if self.inverted:
                volume = 1 - volume
            app.set_volume(volume)

    def get_port(self):
        ports = list_ports.comports()
        device_name = self.get_setting("device name")
        for port, desc, hwid in sorted(ports):
            if device_name in desc:
                return port
        else:
            try:
                return self.get_setting("port")
            except:
                raise ValueError("The config file does not contain the right device name or an appropriate port.")