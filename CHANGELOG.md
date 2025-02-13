## CHANGELOG

### **[v0.0.2]**
#### **Changed**
- **Refactored Environment Variable Handling**  
  - Replaced manual `os.getenv()` calls with default parameter values to simplify code.
  
- **Improved Logging Mechanism**  
  - Integrated `logging` for better logging instead of `print()`, improving debugging and monitoring.
  - All logs now follow a structured format with timestamps.

- **Database Initialization Improvements**  
  - Ensured that the database directory is created if missing.
  - Wrapped database initialization inside a `with` statement to ensure proper connection handling.
  - Removed redundant `conn` variable, now using connections inside `with` statements.

- **Optimized Match Tracking**  
  - Moved logic to detect new matches into `parse_status()`.
  - Automatically ends the previous match when a new match starts.
  - Improved handling of map changes and timeouts.
  - Extracted player score updates into a separate function.

- **Refactored Player Score Updates**  
  - Instead of inserting new rows, now updates existing player scores when necessary.
  - Prevents duplicate records in the `player_stats` table.
  - Logs score updates only if they changed.

- **Enhanced RCON Command Handling**  
  - Improved error handling and logging in `send_rcon_command()`.
  - Reduced redundant delays in socket communication.

- **Refactored Match End Handling**  
  - `end_match()` now properly updates match statistics before closing.
  - Fetches total frags and best player in a single function call.

- **Code Cleanup & Readability Improvements**  
  - Removed unnecessary global variables.
  - Simplified function names and removed redundant comments.
  - Consolidated multiple `sqlite3.connect()` calls using `with` statements.

#### **Removed**
- **Removed Global Database Connection (`conn`)**  
  - Now using `with sqlite3.connect(DB_PATH) as conn:` to ensure proper connection handling.
  
- **Removed Redundant Socket Initialization Function**  
  - `init_socket()` function removed; socket is now initialized inside `monitor_server()`.
