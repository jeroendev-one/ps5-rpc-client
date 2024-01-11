import rpc
import time
import socket
import os
import json
import requests
from time import mktime

# Get the current timestamp
current_time = time.strftime('%H:%M:%S')

client_id = os.getenv('DISCORD_CLIENT_ID')  # Your application's client ID as a string.
PS5_IP = os.getenv('PS5_IP')  # Replace with your PS5's IP address. Be sure you make it static
PS5_RPC_PORT_str = os.getenv('PS5_RPC_PORT', default='8000')   # Replace with your PS5's RPC port

# Convert to integer
PS5_RPC_PORT = int(PS5_RPC_PORT_str)

# Function to load game info from 'game_info.json' file
def load_game_info():
    try:
        with open('game_info.json', 'r') as file:
            return json.load(file)
    except FileNotFoundError:
        return {}  # Return an empty dictionary if the file doesn't exist

previous_game = None  # Store the previous game ID
game_info = load_game_info()

# Function to connect to the TCP server
def connect_to_server(ip, port):
    try:
        client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client_socket.connect((ip, port))
        return client_socket
    except socket.error as e:
        print(f"[{current_time}] Error connecting to server: {e}")
        return None

print(f"[{current_time}] PS5 RPC Discord client started --\n")


while True:
    try:
        # Attempt to initialize the Discord IPC client
        rpc_obj = rpc.DiscordIpcClient.for_platform(client_id)
        print(f"[{current_time}] RPC connection to Discord successful.\n")
        break  # Exit the loop if successful

    except Exception as e:
        print(f"[{current_time}] Error initializing Discord IPC socket: {e}")
        print(f"[{current_time}] Waiting for Discord IPC socket...\n")
        time.sleep(5)  # Wait for a few seconds before retrying

# Connect to PS5's RPC server
ps5_socket = None
while ps5_socket is None:
    ps5_socket = connect_to_server(PS5_IP, PS5_RPC_PORT)
    if ps5_socket is None:
        print(f"[{current_time}] PS5 RPC server unavailable, retrying in 5 seconds\n")
        time.sleep(5)  # Wait and try again if connection failed

start_time = mktime(time.localtime())

while True:
    try:
        # Receive data from PS5's RPC server
        data = ps5_socket.recv(1024).decode("utf-8").strip()
        normalized_data = data.rstrip('\n')

        print(f"[{current_time}] Data received: {data}\n")

        if not "game" in normalized_data:
            if normalized_data != previous_game:
                previous_game = normalized_data

                if normalized_data in game_info:
                    # Use saved game info
                    print(f"[{current_time}] Game found in game_info.json for data: {data}\n")
                    gameName = game_info[normalized_data]['gameName']
                    gameImage = game_info[normalized_data]['gameImage']

                else:
                    params = {
                        'titleid': data,
                    }
                    
                    if 'CUSA' in normalized_data:
                        baseurl = 'https://orbispatches.com/api/lookup'

                    elif 'PPSA' in normalized_data:
                        baseurl = 'https://prosperopatches.com/api/lookup'
                        
                    response = requests.get(baseurl, params=params)
                    response_json = response.json()
                    gameName = response_json['metadata']['name']
                    gameImage = response_json['metadata']['icon']

                    # Store game info in the dictionary without newline characters
                    game_info[normalized_data] = {'gameName': gameName, 'gameImage': gameImage}

                    # Save game info to a JSON file
                    with open('game_info.json', 'w') as file:
                        json.dump(game_info, file, indent=4)

                # Set gameName as activity state and gameImage as assets large_image
                activity = {
                    "state": data,
                    "details": gameName,
                    "timestamps": {
                        "start": mktime(time.localtime())
                    },
                    "assets": {
                        "large_image": gameImage if gameImage else "default_image"  # Use a default image if gameImage is None
                    }
                }

                rpc_obj.set_activity(activity)
                print(f"[{current_time}] Updated activity")
            else:
                print(f"[{current_time}] Latest data matches current. Not updating.\n")
        else:
            details = 'Idle'

    except socket.error as e:
        print(f"Socket error: {e}")
        ps5_socket.close()  # Close the socket on error
        ps5_socket = None  # Reset the socket object

        print(f"[{current_time}] Lost connection to the PS5, waiting for it to come back.")
        while ps5_socket is None:
            ps5_socket = connect_to_server(PS5_IP, PS5_RPC_PORT)
            if ps5_socket is None:
                print(f"[{current_time}] PS5 RPC server still unavailable, retrying in 5 seconds")
                time.sleep(5)  # Wait and try again if connection failed