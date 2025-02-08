from flask import Flask, render_template
import sqlite3
import os

# Read database path from environment variable (default: /app/db/quake_stats.db)
DB_PATH = os.getenv("DB_PATH", "/app/db/quake_stats.db")

app = Flask(__name__)

# Database connection function
def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/')
def index():
    conn = get_db_connection()

    # Get last 5 matches
    matches = conn.execute('''
        SELECT id, map, start_time, end_time, total_frags, best_player, best_score
        FROM matches 
        ORDER BY start_time DESC 
        LIMIT 5
    ''').fetchall()

    # Get top players by total frags
    players = conn.execute('''
        SELECT player_name, SUM(score) AS total_score
        FROM player_stats
        GROUP BY player_name
        ORDER BY total_score DESC
        LIMIT 10
    ''').fetchall()

    # Get most active players (matches played)
    active_players = conn.execute('''
        SELECT player_name, COUNT(DISTINCT match_id) AS matches_played
        FROM player_stats
        GROUP BY player_name
        ORDER BY matches_played DESC
        LIMIT 10
    ''').fetchall()

    # Get win rate (matches won)
    win_rates = conn.execute('''
        SELECT player_name, COUNT(*) AS match_wins
        FROM player_stats
        WHERE score = (SELECT MAX(score) FROM player_stats WHERE match_id = player_stats.match_id)
        GROUP BY player_name
        ORDER BY match_wins DESC
        LIMIT 10
    ''').fetchall()

    # Get best maps per player
    best_maps = conn.execute('''
        SELECT player_name, map, AVG(score) AS avg_score
        FROM player_stats
        JOIN matches ON player_stats.match_id = matches.id
        GROUP BY player_name, map
        ORDER BY avg_score DESC
        LIMIT 10
    ''').fetchall()

    # Get peak activity hours
    peak_hours = conn.execute('''
        SELECT strftime('%H', start_time) AS hour, COUNT(*) AS match_count
        FROM matches
        GROUP BY hour
        ORDER BY match_count DESC
        LIMIT 5
    ''').fetchall()

    conn.close()

    return render_template('index.html', matches=matches, players=players, active_players=active_players, win_rates=win_rates, best_maps=best_maps, peak_hours=peak_hours)

if __name__ == '__main__':
    app.run(debug=True, host="0.0.0.0", port=5000)
