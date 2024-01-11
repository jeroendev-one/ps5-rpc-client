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

# Default variables
fallback_image = 'https://github.com/jeroendev-one/ps5-rpc-client/raw/main/assets/fallback_ps5.webp'
PS5_RPC_PORT = 8000
DISCORD_CLIENT_ID = None  # Initialize outside the try block
PS5_IP = None  # Initialize outside the try block

# Load config from config.ini, if not present ask for input and create the file
def get_ini_config():
    config = configparser.ConfigParser()

    try:
        with open('config.ini') as f:
            config.read_file(f)
            if not config.has_section('settings'):
                print("Error: invalid config.ini file!")
                sys.exit(1)
            else:
                print(config['settings']['client_id'])
                print(config['settings']['ps5_ip'])
                DISCORD_CLIENT_ID = config['settings']['client_id']
                PS5_IP = config['settings']['ps5_ip']
                
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

        config['settings'] = {'client_id': DISCORD_CLIENT_ID,
                             'ps5_ip': PS5_IP}
        with open('config.ini', 'w') as f:
            config.write(f)

    return DISCORD_CLIENT_ID, PS5_IP

# Initialize INI config parsing
DISCORD_CLIENT_ID, PS5_IP = get_ini_config()

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
    params = {'titleid': data}
    if 'CUSA' in normalized_data:
        baseurl = 'https://orbispatches.com/api/lookup'
    elif 'PPSA' in normalized_data:
        baseurl = 'https://prosperopatches.com/api/lookup'
    else:
        return normalized_data, None # No baseurl defined, return recieved value for gameName and non gameImage

    response = requests.get(baseurl, params=params)
    response_json = response.json()
    gameName = response_json['metadata']['name']
    gameImage = response_json['metadata']['icon']

    return gameName, gameImage


# Function to connect to the etaHEN TCP server
def connect_to_server(ip, port):
    try:
        client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client_socket.connect((ip, port))
        return client_socket
    except socket.error as e:
        print(f"[{get_time()}] Error connecting to server: {e}")
        return None

# Initialize Discord IPC client
print(f"[{get_time()}] PS5 RPC Discord client started --\n")
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
        # Check if there is data to be read
        ready_to_read, _, _ = select.select([ps5_socket.fileno()], [], [], 30)

        if ready_to_read:
            data = ps5_socket.recv(1024).decode("utf-8").strip()
            normalized_data = data.rstrip('\n')

            print(f"[{get_time()}] Data received: {data}\n")

            if normalized_data != previous_data:
                previous_data = normalized_data

                if not "No game running" in normalized_data:
                    if normalized_data in game_info:
                        print(f"[{get_time()}] Game found in game_info.json for data: {data}\n")
                        gameName = game_info[normalized_data]['gameName']
                        gameImage = game_info[normalized_data]['gameImage']
                    else:
                        gameName, gameImage = get_game_info(data, normalized_data)

                        if gameName is not None and gameImage is not None:
                            game_info[normalized_data] = {'gameName': gameName, 'gameImage': gameImage}
                            with open('game_info.json', 'w') as file:
                                json.dump(game_info, file, indent=4)

                    activity = {
                        "details": gameName,
                        "timestamps": {"start": mktime(time.localtime())},
                        "assets": {
                            "large_image": gameImage if gameImage else fallback_image
                        }
                    }

                    rpc_obj.set_activity(activity)
                    print(f"[{get_time()}] Updated activity")
                else:
                    activity = {
                        "details": "Idle",
                        "timestamps": {"start": mktime(time.localtime())},
                        "assets": {
                            "large_image": fallback_image
                        }
                    }

                    rpc_obj.set_activity(activity)
                    print(f"[{get_time()}] Updated activity for 'No game running'")
            else:
                print(f"[{get_time()}] Previous data matches current. Not updating activity.\n")
        else:
            print(f"[{get_time()}] No data received in the last 30 seconds. Reconnecting...\n")
            ps5_socket.close()
            ps5_socket = None

            # Outside of the 'while True' loop, attempt to reconnect
            while ps5_socket is None:
                ps5_socket = connect_to_server(PS5_IP, PS5_RPC_PORT)
                if ps5_socket is None:
                    print(f"[{get_time()}] PS5 RPC server still unavailable, retrying in 5 seconds.")
                    time.sleep(5)

    except socket.error as e:
        if e.errno == errno.EAGAIN or e.errno == errno.EWOULDBLOCK:
            # No data available, continue the loop
            continue
        elif e.errno == errno.ECONNRESET or e.errno == errno.ENOTCONN:
            print(f"Connection reset by peer or not connected: {e}")
        else:
            print(f"Socket error: {e}")

        ps5_socket.close()
        ps5_socket = None

        print(f"[{get_time()}] Lost connection to the PS5, waiting for it to come back.")
        while ps5_socket is None:
            ps5_socket = connect_to_server(PS5_IP, PS5_RPC_PORT)
            if ps5_socket is None:
                print(f"[{get_time()}] PS5 RPC server still unavailable, retrying in 5 seconds.")
                time.sleep(5)