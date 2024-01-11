import rpc
import time
import socket
import os
import json
import requests
from time import mktime

# Get the current timestamp
current_time = time.strftime('%H:%M:%S')

# Default variables
fallback_image = 'https://github.com/jeroendev-one/ps5-rpc-client/raw/main/assets/fallback_ps5.webp'
PS5_RPC_PORT = 8000

# User specific variabls
client_id = os.getenv('DISCORD_CLIENT_ID')  # Your application's client ID as a string.
PS5_IP = os.getenv('PS5_IP')  # Replace with your PS5's IP address. Be sure you make it static

# Function to load game info from 'game_info.json' file
def load_game_info():
    try:
        with open('game_info.json', 'r') as file:
            return json.load(file)
    except FileNotFoundError:
        return {}  # Return an empty dictionary if the file doesn't exist

# Function to connect to the TCP server
def connect_to_server(ip, port):
    try:
        client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client_socket.connect((ip, port))
        return client_socket
    except socket.error as e:
        print(f"[{current_time}] Error connecting to server: {e}")
        return None

# Initialize Discord IPC client
print(f"[{current_time}] PS5 RPC Discord client started --\n")
while True:
    try:
        rpc_obj = rpc.DiscordIpcClient.for_platform(client_id)
        print(f"[{current_time}] RPC connection to Discord successful.\n")
        break
    except Exception as e:
        print(f"[{current_time}] Error initializing Discord IPC socket: {e}")
        print(f"[{current_time}] Waiting for Discord IPC socket...\n")
        time.sleep(5)

# Connect to PS5's RPC server
ps5_socket = None
while ps5_socket is None:
    ps5_socket = connect_to_server(PS5_IP, PS5_RPC_PORT)
    if ps5_socket is None:
        print(f"[{current_time}] PS5 RPC server unavailable, retrying in 5 seconds\n")
        time.sleep(5)

# Initialization
previous_game = None
game_info = load_game_info()

start_time = mktime(time.localtime())

# Main loop
while True:
    try:
        data = ps5_socket.recv(1024).decode("utf-8").strip()
        normalized_data = data.rstrip('\n')

        print(f"[{current_time}] Data received: {data}\n")

        if not "No game running" in normalized_data:
            if normalized_data != previous_data:
                previous_data = normalized_data

                if normalized_data in game_info:
                    print(f"[{current_time}] Game found in game_info.json for data: {data}\n")
                    gameName = game_info[normalized_data]['gameName']
                    gameImage = game_info[normalized_data]['gameImage']

                else:
                    params = {'titleid': data}
                    if 'CUSA' in normalized_data:
                        baseurl = 'https://orbispatches.com/api/lookup'
                    elif 'PPSA' in normalized_data:
                        baseurl = 'https://prosperopatches.com/api/lookup'
                    
                    response = requests.get(baseurl, params=params)
                    response_json = response.json()
                    gameName = response_json['metadata']['name']
                    gameImage = response_json['metadata']['icon']

                    game_info[normalized_data] = {'gameName': gameName, 'gameImage': gameImage}
                    with open('game_info.json', 'w') as file:
                        json.dump(game_info, file, indent=4)

                activity = {
                    "details": gameName,
                    "timestamps": {"start": mktime(time.localtime())},
                    "assets": {
                        "large_image": gameImage if gameImage else "fallback_image"
                    }
                }

                rpc_obj.set_activity(activity)
                print(f"[{current_time}] Updated activity")
            else:
                print(f"[{current_time}] Previous data matches current. Not updating activity.\n")
        else:
            activity = {
                "details": "Idle",
                "assets": {
                    "large_image": fallback_image
                }
            }

            rpc_obj.set_activity(activity)

    except socket.error as e:
        print(f"Socket error: {e}")
        ps5_socket.close()
        ps5_socket = None

        print(f"[{current_time}] Lost connection to the PS5, waiting for it to come back.")
        while ps5_socket is None:
            ps5_socket = connect_to_server(PS5_IP, PS5_RPC_PORT)
            if ps5_socket is None:
                print(f"[{current_time}] PS5 RPC server still unavailable, retrying in 5 seconds.")
                time.sleep(5)
