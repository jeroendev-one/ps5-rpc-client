import rpc
import time
import socket
import os
import json
import requests
import configparser
import sys
import select
import errno
from time import mktime
from json.decoder import JSONDecodeError

# Suppress InsecureRequestWarning for the requests module
requests.packages.urllib3.disable_warnings(requests.packages.urllib3.exceptions.InsecureRequestWarning)

# Default variables
fallback_image = 'https://github.com/jeroendev-one/ps5-rpc-client/raw/main/assets/fallback_ps5.webp'
PS5_RPC_PORT = 8000
DISCORD_CLIENT_ID = None
PS5_IP = None
BUTTONS=False

# Load config from config.ini, if not present ask for input and create the file
def get_ini_config():
    global BUTTONS  # Add this line
    config = configparser.ConfigParser()

    try:
        with open('config.ini') as f:
            config.read_file(f)
            if not config.has_section('settings'):
                print("Error: invalid config.ini file!")
                sys.exit(1)
            else:
                DISCORD_CLIENT_ID = config['settings']['client_id']
                PS5_IP = config['settings']['ps5_ip']
                BUTTONS = config['settings']['buttons']
                
    except FileNotFoundError:
        print("First setup detected!")

        DISCORD_CLIENT_ID = input("Enter Discord Application ID: ")
        while not DISCORD_CLIENT_ID.strip():
            print("Please enter a non-empty value.")
            DISCORD_CLIENT_ID = input("Enter Discord Application ID: ")

        PS5_IP = input("Enter PS5 IP address: ")
        while not PS5_IP.strip():
            print("Please enter a non-empty value.")
            PS5_IP = input("Enter PS5 IP address: ")

        BUTTONS = input("Do you want buttons enabled? (yes/no): ").lower()
        while BUTTONS not in ['yes', 'no']:
            print("Please enter 'yes' or 'no'.")
            BUTTONS = input("Do you want buttons enabled? (yes/no): ").lower()

        # Convert the string 'yes' or 'no' to boolean True or False
        BUTTONS = BUTTONS == 'yes'

        config['settings'] = {'client_id': DISCORD_CLIENT_ID,
                            'ps5_ip': PS5_IP,
                            'buttons': '1' if BUTTONS == 'yes' else '0'}

        with open('config.ini', 'w') as f:
            config.write(f)


    return DISCORD_CLIENT_ID, PS5_IP, BUTTONS

# Initialize INI config parsing
DISCORD_CLIENT_ID, PS5_IP, BUTTONS = get_ini_config()

# Function to get formatted timestamp
def get_time():
    return time.strftime('%H:%M:%S')

# Function to load game info from 'game_info.json' file or URL
def load_game_info():
    local_file_path = 'game_info.json'
    url = 'https://raw.githubusercontent.com/jeroendev-one/ps5-rpc-client/main/game_info.json'

    try:
        with open(local_file_path, 'r') as file:
            return json.load(file)
    except FileNotFoundError:
        try:
            print(f"[{get_time()}] game_info.json not found, retrieving from Github")
            response = requests.get(url)
            response.raise_for_status()  # Raise an exception when responses != 200
            
            game_info = response.json()

            # Write the retrieved data to the local file
            with open(local_file_path, 'w') as file:
                json.dump(game_info, file, indent=4)

            return game_info
        except (FileNotFoundError, JSONDecodeError, requests.RequestException) as e:
            print(f"Error loading game info: {e}")
            return {}

# Function to get game info from the API
def get_game_info(data, normalized_data):
    params = {}
    gameUrl = None  # Initialize gameUrl to None

    if 'CUSA' in normalized_data:
        baseUrl = 'https://orbispatches.com/api/lookup'
        gameUrl = f'https://orbispatches.com/{data}'
        type = 'Retail'
        
    elif 'PPSA' in normalized_data:
        baseUrl = 'https://prosperopatches.com/api/lookup'
        type = 'Retail'
        
    elif len(normalized_data) == 9 and 'NPXS' not in normalized_data:
        baseUrl = f'https://api.pkg-zone.com/pkg/cusa/{data}'
        gameUrl = f'https://pkg-zone.com/details/{data}'
        proxyUrl = 'http://62.210.38.117:6443/'
        type = 'Homebrew'
        
    else:
        return normalized_data, fallback_image, gameUrl

    try:
        if type == 'Retail':
            params = {'titleid': data}
            response = requests.get(baseUrl, params=params)
            response.raise_for_status()  # Raise an HTTPError
            response_json = response.json()
            gameName = response_json['metadata']['name']
            gameImage = response_json['metadata']['icon']

        elif type == 'Homebrew':
            headers = {'User-Agent': 'StoreHAX'}
            response = requests.get(baseUrl, headers=headers, verify=False)
            response.raise_for_status()  # Raise an HTTPError
            response_json = response.json()
            gameName = response_json['items'][0]['name']
            image = response_json['items'][0]['attachments'][0]['path']
            gameImage = f'{proxyUrl}{image}'

        return gameName, gameImage, gameUrl

    except requests.exceptions.HTTPError as http_err:
        print(f"HTTP error occurred: {http_err}")
        print("Falling back to default")
        gameName = normalized_data
        gameImage = fallback_image
        gameUrl = ''
        
    return gameName, gameImage, gameUrl


# Function to connect to the etaHEN TCP server
def connect_to_server(ip, port):
    try:
        client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client_socket.connect((ip, port))
        return client_socket
    except socket.error as e:
        print(f"[{get_time()}] Error connecting to server: {e}")
        return None

# Function to set Discord activity
def set_discord_activity(rpc_obj, gameName, gameImage, gameUrl, BUTTONS):
    activity = {
        "details": gameName,
        "timestamps": {"start": mktime(time.localtime())},
        "assets": {
            "large_image": gameImage
        },
    }

    if BUTTONS and gameUrl:
        # Append buttons section
        activity["buttons"] = [{"label": "View game", "url": gameUrl}]

    rpc_obj.set_activity(activity)
    print(f"[{get_time()}] Updated activity{' for ' + gameName}")

# Initialize Discord IPC client
print(f"[{get_time()}] -- PS5 RPC Discord client started --\n")
while True:
    try:
        rpc_obj = rpc.DiscordIpcClient.for_platform(DISCORD_CLIENT_ID)
        print(f"[{get_time()}] RPC connection to Discord successful.\n")
        break
    except Exception as e:
        print(f"[{get_time()}] Error initializing Discord IPC socket: {e}")
        print(f"[{get_time()}] Waiting for Discord IPC socket...\n")
        time.sleep(5)

# Connect to PS5's RPC server
ps5_socket = None
while ps5_socket is None:
    ps5_socket = connect_to_server(PS5_IP, PS5_RPC_PORT)
    if ps5_socket is None:
        print(f"[{get_time()}] PS5 RPC server unavailable, retrying in 5 seconds\n")
        time.sleep(5)

# Initialization
previous_data = None
game_info = load_game_info()

start_time = mktime(time.localtime())

# Set the socket to non-blocking
ps5_socket.setblocking(0)

# Main loop
while True:
    try:
        # Receive data
        data = ps5_socket.recv(1024).decode("utf-8").strip()
        normalized_data = data.rstrip('\n')

        if not normalized_data:
            count_empty_data += 1
            time.sleep(5)

            if count_empty_data == 6:
                print(f"[{get_time()}] No data received in the last 30 seconds. Reconnecting...\n")
                ps5_socket.close()
                ps5_socket = None

                # Attempt to reconnect
                while ps5_socket is None:
                    ps5_socket = connect_to_server(PS5_IP, PS5_RPC_PORT)
                    if ps5_socket is None:
                        print(f"[{get_time()}] PS5 RPC server still unavailable, retrying in 5 seconds.\n")
                        time.sleep(5)
                count_empty_data = 0
            continue
        else:
            count_empty_data = 0  # Reset the count when data is received

        print(f"[{get_time()}] Data received: {data}\n")

        if normalized_data != previous_data:
            previous_data = normalized_data

            if "No game running" in normalized_data:
                normalized_data = 'NO_GAME_RUNNING'

            if normalized_data in game_info:
                print(f"[{get_time()}] Game found in game_info.json for data: {data}\n")
                gameUrl = game_info[normalized_data]['gameUrl']

                if not gameUrl:
                    BUTTONS=False
                
                gameName = game_info[normalized_data]['gameName']
                gameImage = game_info[normalized_data]['gameImage']
                set_discord_activity(rpc_obj, gameName, gameImage, gameUrl, BUTTONS == 1)
            else:
                gameName, gameImage, gameUrl = get_game_info(data, normalized_data)

                if gameName is not None and gameImage is not None and gameUrl is not None:
                    game_info[normalized_data] = {'gameName': gameName, 'gameImage': gameImage, 'gameUrl': gameUrl}
                    with open('game_info.json', 'w') as file:
                            json.dump(game_info, file, indent=4)

                set_discord_activity(rpc_obj, gameName, gameImage, gameUrl, BUTTONS == 1)
        else:
            print(f"[{get_time()}] Previous data matches current. Not updating activity.\n")

    except socket.error as e:
            if e.errno == errno.ECONNRESET or e.errno == errno.ENOTCONN:
                print(f"Connection reset by peer or not connected: {e}")
                # Close the socket and try to reconnect immediately
                ps5_socket.close()
                ps5_socket = None
                while ps5_socket is None:
                    ps5_socket = connect_to_server(PS5_IP, PS5_RPC_PORT)
                    if ps5_socket is None:
                        print(f"[{get_time()}] PS5 RPC server still unavailable, retrying in 5 seconds.\n")
                        time.sleep(5)
            else:
                print(f"Socket error: {e}")
                # Close the socket and try to reconnect immediately
                ps5_socket.close()
                ps5_socket = None
                while ps5_socket is None:
                    ps5_socket = connect_to_server(PS5_IP, PS5_RPC_PORT)
                    if ps5_socket is None:
                        print(f"[{get_time()}] PS5 RPC server still unavailable, retrying in 5 seconds.\n")
                        time.sleep(5)