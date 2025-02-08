import os
import socket
import time
import re
import sqlite3
import signal
import sys
from datetime import datetime

# Read configurations from environment variables
SERVER_IP = os.getenv("SERVER_IP") or "quakejs-proxy"
SERVER_PORT = int(os.getenv("SERVER_PORT") or 27960)
RCON_PASSWORD = os.getenv("RCON_PASSWORD") or "5tr0nG_P@ssw0rd!"
COMMAND = os.getenv("RCON_COMMAND") or "status"
TRACKED_PLAYERS = set((os.getenv("TRACKED_PLAYERS", "batman,robin,penguin")).split(","))
MATCH_TIMEOUT = int(os.getenv("MATCH_TIMEOUT") or 3600)  # 1 hour (default)
DB_PATH = os.getenv("DB_PATH") or "/app/db/quake_stats.db"
RUNNING = True  # Flag to control loop execution

# Global tracking variables
LAST_MAP = None
LAST_PLAYERS = {}
MATCH_ACTIVE = False

# Database connection (global)
conn = None

# Global socket connection
sock = None

def init_db():
    global conn
    
    # Ensure the directory exists
    db_dir = os.path.dirname(DB_PATH)
    if not os.path.exists(db_dir):
        print(f"📁 Creating database directory: {db_dir}")
        os.makedirs(db_dir, exist_ok=True)

    # Connect to SQLite and create tables
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute('''
        CREATE TABLE IF NOT EXISTS matches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            map TEXT,
            start_time TEXT,
            end_time TEXT,
            total_frags INTEGER DEFAULT 0,
            best_player TEXT,
            best_score INTEGER DEFAULT 0
        )
    ''')

    cur.execute('''
        CREATE TABLE IF NOT EXISTS player_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            match_id INTEGER,
            player_name TEXT,
            score INTEGER,
            FOREIGN KEY (match_id) REFERENCES matches(id),
            UNIQUE (match_id, player_name)
        )
    ''')

    conn.commit()
    print("✅ Database initialized successfully.")

# Graceful shutdown function
def shutdown_handler(signum, frame):
    global RUNNING, sock
    print("\n🛑 Received shutdown signal. Cleaning up...")
    RUNNING = False  # Stop the loop gracefully
    if conn:
        conn.close()  # Ensure database connection is closed
    if sock:
        sock.close()  # Close the socket connection
    print("🛑 QuakeJS Monitor stopped.")
    sys.exit(0)

# Register signal handlers for SIGINT (CTRL+C) and SIGTERM (kill command)
signal.signal(signal.SIGINT, shutdown_handler)
signal.signal(signal.SIGTERM, shutdown_handler)

# Initialize socket connection
def init_socket():
    global sock
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(2)

# Send RCON Command and Parse Response
def send_rcon_command():
    try:
        request = b"\xFF\xFF\xFF\xFF" + f"rcon {RCON_PASSWORD} {COMMAND}".encode("utf-8")
        sock.sendto(request, (SERVER_IP, SERVER_PORT))

        time.sleep(0.5)  # Short delay

        response, _ = sock.recvfrom(4096)
        return response.decode("utf-8", errors="ignore")

    except socket.timeout:
        print(f"❌ [ERROR] No response from server. Connection timeout.")
        return None
    except Exception as e:
        print(f"❌ [ERROR] {e}")
        return None

# Remove Quake3 Color Codes (^7, ^1, etc.)
def clean_name(name):
    return re.sub(r"\^\d", "", name)

# Get last match ID, start time, and map name
def get_last_match():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute('SELECT id, start_time, map FROM matches ORDER BY id DESC LIMIT 1')
    match = cur.fetchone()
    conn.close()

    if match:
        match_id = match[0]
        match_time = datetime.strptime(match[1], "%Y-%m-%d %H:%M:%S").timestamp()
        map_name = match[2]
        return match_id, match_time, map_name
    return None, 0, None

# Parse the RCON `status` output
def parse_status(response):
    global LAST_MAP, LAST_PLAYERS, MATCH_ACTIVE

    if not response:
        return None, {}

    lines = response.split("\n")
    map_name = None
    players = {}

    # Extract map name
    for line in lines:
        if line.startswith("map:"):
            map_name = line.split(":")[1].strip()

    # Extract players
    player_pattern = re.compile(r"^\s*(\d+)\s+(-?\d+)\s+\d+\s+(.+?)\s+[\d\.]+")

    for line in lines:
        match = player_pattern.match(line)
        if match:
            player_name = clean_name(match.group(3).strip())
            score = int(match.group(2))

            # Only track specific players
            if player_name in TRACKED_PLAYERS:
                players[player_name] = score

    # Get last match info
    last_match_id, last_match_time, last_map = get_last_match()
    current_time = time.time()

    # 🏁 **Detect New Match (if map changed OR timeout passed)**
    if last_map is None or map_name != last_map or (current_time - last_match_time > MATCH_TIMEOUT):
        if last_match_id and last_map != map_name:
            print(f"🔄 Ending previous match: {last_match_id} on {last_map}")
            end_match(last_match_id)

        MATCH_ACTIVE = True
        match_id = save_new_match(map_name)
        print(f"🏁 New match started on map: {map_name}")
    else:
        match_id = last_match_id

    # **Update only if scores changed**
    if players and players != LAST_PLAYERS:
        update_scores(match_id, players)

    # **Log current tracked scores (only if they changed)**
    if players and players != LAST_PLAYERS:
        print("📊 Updated Scores:")
        for player, score in players.items():
            print(f"   {player}: {score} frags")

    # **Update tracking variables**
    LAST_MAP = map_name
    LAST_PLAYERS = players

    return match_id, players

# Save new match
def save_new_match(map_name):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    start_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cur.execute('INSERT INTO matches (map, start_time) VALUES (?, ?)', (map_name, start_time))
    match_id = cur.lastrowid  # Get last inserted match ID

    conn.commit()
    conn.close()
    return match_id

# End match when the map changes
def end_match(match_id):
    if match_id is None:
        return
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    end_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Calculate total frags & best player
    cur.execute('SELECT player_name, MAX(score) FROM player_stats WHERE match_id = ?', (match_id,))
    best_player = cur.fetchone()
    best_player_name, best_score = best_player if best_player else (None, 0)

    cur.execute('SELECT SUM(score) FROM player_stats WHERE match_id = ?', (match_id,))
    total_frags = cur.fetchone()[0] or 0

    cur.execute('''
        UPDATE matches 
        SET end_time = ?, total_frags = ?, best_player = ?, best_score = ? 
        WHERE id = ? AND end_time IS NULL
    ''', (end_time, total_frags, best_player_name, best_score, match_id))

    conn.commit()
    conn.close()

# Update player scores (instead of inserting new rows)
def update_scores(match_id, players):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    for player_name, score in players.items():
        cur.execute('SELECT score FROM player_stats WHERE match_id = ? AND player_name = ?', (match_id, player_name))
        existing = cur.fetchone()

        if existing:
            if existing[0] != score:
                cur.execute('UPDATE player_stats SET score = ? WHERE match_id = ? AND player_name = ?',
                            (score, match_id, player_name))
        else:
            cur.execute('INSERT INTO player_stats (match_id, player_name, score) VALUES (?, ?, ?)',
                        (match_id, player_name, score))

    conn.commit()
    conn.close()

# Loop to continuously monitor matches
def monitor_server():
    global sock
    print("🚀 QuakeJS Monitor started. Tracking players:", ", ".join(TRACKED_PLAYERS))
    init_db()
    init_socket()
    while RUNNING:
        raw_response = send_rcon_command()
        if raw_response:
            parse_status(raw_response)
        time.sleep(2)  # Update every 2 seconds

if __name__ == "__main__":
    monitor_server()
