import os
import socket
import time
import re
import sqlite3
import signal
import sys
import logging
from datetime import datetime

# Configuration
SERVER_IP = os.getenv("SERVER_IP", "quakejs-proxy")
SERVER_PORT = int(os.getenv("SERVER_PORT", 27960))
RCON_PASSWORD = os.getenv("RCON_PASSWORD", "5tr0nG_P@ssw0rd!")
COMMAND = os.getenv("RCON_COMMAND", "status")
TRACKED_PLAYERS = set(os.getenv("TRACKED_PLAYERS", "Visor,Sarge,Major").split(","))
MATCH_TIMEOUT = int(os.getenv("MATCH_TIMEOUT", 3600))  # Default: 1 hour
DB_PATH = os.getenv("DB_PATH", "/app/db/quake_stats.db")
RUNNING = True

# Global Variables
LAST_MAP = None
LAST_PLAYERS = {}
MATCH_ACTIVE = False
sock = None

# Logging setup
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Remove Quake3 color codes (^7, ^1, etc.)
def clean_name(name):
    return re.sub(r"\^\d", "", name).strip()

# Initialize the database
def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute('''
            CREATE TABLE IF NOT EXISTS matches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                map TEXT,
                start_time TEXT,
                end_time TEXT DEFAULT NULL,
                total_frags INTEGER DEFAULT 0,
                best_player TEXT DEFAULT NULL,
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
    logging.info("✅ Database initialized successfully.")

# Graceful shutdown handler
def shutdown_handler(signum, frame):
    global RUNNING, sock
    logging.info("🛑 Shutting down...")
    RUNNING = False
    if sock:
        sock.close()
    sys.exit(0)

signal.signal(signal.SIGINT, shutdown_handler)
signal.signal(signal.SIGTERM, shutdown_handler)

# Send an RCON command to the QuakeJS server
def send_rcon_command():
    try:
        request = b"\xFF\xFF\xFF\xFF" + f"rcon {RCON_PASSWORD} {COMMAND}".encode()
        sock.sendto(request, (SERVER_IP, SERVER_PORT))
        response, _ = sock.recvfrom(4096)
        return response.decode("utf-8", errors="ignore")
    except socket.timeout:
        logging.error(f"❌ No response from server ({SERVER_IP}:{SERVER_PORT}).")
        return None

# Get the last match from the database
def get_last_match():
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute('SELECT id, start_time, map FROM matches ORDER BY id DESC LIMIT 1')
        match = cur.fetchone()
    if match:
        return match[0], datetime.strptime(match[1], "%Y-%m-%d %H:%M:%S").timestamp(), match[2]
    return None, 0, None

# End a match and update its stats
def end_match(match_id):
    if not match_id:
        return
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute('SELECT player_name, MAX(score) FROM player_stats WHERE match_id = ?', (match_id,))
        best_player = cur.fetchone()
        cur.execute('SELECT SUM(score) FROM player_stats WHERE match_id = ?', (match_id,))
        total_frags = cur.fetchone()[0] or 0
        cur.execute('''
            UPDATE matches SET end_time = ?, total_frags = ?, best_player = ?, best_score = ?
            WHERE id = ? AND end_time IS NULL
        ''', (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), total_frags, *best_player, match_id))
        conn.commit()

# Update player scores in the database
def update_scores(match_id, players):
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        for player_name, score in players.items():
            cur.execute('SELECT score FROM player_stats WHERE match_id = ? AND player_name = ?', (match_id, player_name))
            existing = cur.fetchone()
            if existing:
                prev_score = existing[0]
                if prev_score != score:
                    cur.execute('UPDATE player_stats SET score = ? WHERE match_id = ? AND player_name = ?', (score, match_id, player_name))
                    logging.info(f"📊 {player_name} score updated: {prev_score} → {score}")
            else:
                cur.execute('INSERT INTO player_stats (match_id, player_name, score) VALUES (?, ?, ?)', (match_id, player_name, score))
                logging.info(f"📊 New player tracked: {player_name} with score {score}")
        conn.commit()

# Parse the RCON response from the server
def parse_status(response):
    global LAST_MAP, LAST_PLAYERS

    if not response:
        return None

    lines = response.split("\n")
    map_name, players = None, {}

    for line in lines:
        if line.startswith("map:"):
            map_name = line.split(":")[1].strip()
        match = re.match(r"^\s*(\d+)\s+(-?\d+)\s+\d+\s+(.+?)\s+[\d\.]+", line)
        if match:
            player_name = clean_name(match.group(3))
            if player_name in TRACKED_PLAYERS:
                players[player_name] = int(match.group(2))

    if not players:
        return None

    last_match_id, last_match_time, last_map = get_last_match()
    current_time = time.time()

    if last_map is None or map_name != last_map or (current_time - last_match_time > MATCH_TIMEOUT):
        end_match(last_match_id)
        with sqlite3.connect(DB_PATH) as conn:
            cur = conn.cursor()
            cur.execute('INSERT INTO matches (map, start_time) VALUES (?, ?)', (map_name, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            match_id = cur.lastrowid
            conn.commit()
        logging.info(f"🏁 New match started on map {map_name}")
    else:
        match_id = last_match_id

    # Log player score updates only if they changed
    if players != LAST_PLAYERS:
        update_scores(match_id, players)

    LAST_MAP, LAST_PLAYERS = map_name, players

# Start the monitoring loop
def monitor_server():
    global sock
    init_db()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(2)
    while RUNNING:
        parse_status(send_rcon_command())
        time.sleep(2)

if __name__ == "__main__":
    monitor_server()
