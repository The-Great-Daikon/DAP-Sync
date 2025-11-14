# DAP Music Sync Utility

A Docker-based utility for synchronizing music from a MusicBee-managed library on QNAP NAS to a Sony NW-WM1AM2 Android DAP over network/WiFi. This solution handles metadata (tags, artwork), playlists, and supports multiple sync criteria with daily automation.

## Features

- **Network-based sync**: Syncs music over WiFi using ADB over network
- **MusicBee integration**: Reads MusicBee library XML and playlists
- **Metadata preservation**: Preserves ID3 tags and embeds artwork
- **Playlist support**: Syncs playlists, smart playlists, and custom selections
- **Incremental sync**: Only transfers new or changed files
- **Daily automation**: Scheduled daily syncs via cron
- **Comprehensive logging**: Detailed logs with rotation

## Requirements

### QNAP NAS
- Docker or Container Station installed
- Access to MusicBee library files (Library.xml, playlists, music files)
- Network connectivity to DAP

### Sony NW-WM1AM2 DAP
- Android OS
- ADB over network enabled
- Sufficient storage space
- Connected to same network as NAS

## Installation

### 1. Clone or Download

```bash
cd /path/to/project
```

### 2. Configure MusicBee Library Paths

Locate your MusicBee library files:
- `Library.xml` - Typically in `%AppData%\MusicBee\Library.xml` on Windows
- `Playlists` directory - Typically in `%AppData%\MusicBee\Playlists`
- Music files - Your music library directory

On QNAP NAS, these paths will be different. Determine the actual paths on your NAS.

### 3. Enable ADB on DAP

1. Enable Developer Options on your DAP:
   - Go to Settings > About Device
   - Tap "Build Number" 7 times

2. Enable USB Debugging:
   - Go to Settings > Developer Options
   - Enable "USB Debugging"
   - Enable "Network Debugging" or "ADB over Network"

3. Get DAP IP address:
   - Go to Settings > About Device > Status
   - Note the IP address
   - Or use: `adb shell ip addr show wlan0` (if already connected via USB)

4. Connect via ADB:
   ```bash
   adb connect <DAP_IP>:5555
   adb devices  # Verify connection
   ```

### 4. Configure the Sync Utility

1. Copy example configuration:
   ```bash
   cp config/config.yaml.example config/config.yaml
   cp config/sync-rules.yaml.example config/sync-rules.yaml
   ```

2. Edit `config/config.yaml`:
   ```yaml
   musicbee:
     library_path: /music/musicbee/library  # Path to music files on NAS
     library_xml: /music/musicbee/Library.xml  # Path to Library.xml
     playlists_path: /music/musicbee/Playlists  # Path to Playlists directory
   
   dap:
     ip_address: 192.168.1.100  # Your DAP IP address
     port: 5555  # ADB port
     music_path: /sdcard/Music  # Music path on DAP
   
   sync:
     mode: incremental  # incremental or full
     criteria:
       - entire_library: true
       - playlists: ["Favorites", "Recently Added"]
       - smart_playlists:
           - name: "High Rated"
             rating_min: 4
           - name: "Recent"
             days: 30
   
   schedule:
     enabled: true
     time: "02:00"  # Daily sync time (HH:MM)
   ```

3. Edit `config/sync-rules.yaml` (optional):
   ```yaml
   playlist_mappings:
     "Favorites": "Favorites"
     "Recently Added": "Recent"
   ```

### 5. Update Docker Compose

Edit `docker-compose.yml` and update volume mounts:

```yaml
volumes:
  # Update these paths to match your NAS setup
  - /share/MusicBee/library:/music/musicbee/library:ro
  - /share/MusicBee/Library.xml:/music/musicbee/Library.xml:ro
  - /share/MusicBee/Playlists:/music/musicbee/Playlists:ro
```

### 6. Build and Run

```bash
# Build the Docker image
docker-compose build

# Run the container
docker-compose up -d

# View logs
docker-compose logs -f
```

## Configuration

### Main Configuration (`config/config.yaml`)

#### MusicBee Settings
- `library_path`: Base path to music files on NAS
- `library_xml`: Path to MusicBee Library.xml file
- `playlists_path`: Path to MusicBee Playlists directory

#### DAP Settings
- `ip_address`: IP address of DAP on network
- `port`: ADB port (default: 5555)
- `music_path`: Base path for music on DAP (default: `/sdcard/Music`)

#### Sync Settings
- `mode`: `incremental` (only new/changed files) or `full` (all files)
- `criteria`: List of sync criteria:
  - `entire_library: true` - Sync entire library
  - `playlists: ["Name1", "Name2"]` - Sync specific playlists
  - `smart_playlists`: - Sync based on criteria
    - `rating_min`: Minimum rating
    - `days`: Recent tracks (last N days)
    - `genres`: List of genres
    - `artists`: List of artists
    - `albums`: List of albums
  - `custom`: Custom filter criteria

#### Metadata Settings
- `preserve_tags`: Preserve ID3 tags (default: true)
- `embed_artwork`: Embed artwork in files (default: true)
- `artwork_size`: Maximum artwork dimension in pixels (default: 1000)

#### Schedule Settings
- `enabled`: Enable daily scheduled sync (default: true)
- `time`: Sync time in HH:MM format (default: "02:00")
- `timezone`: Timezone (default: "UTC")

#### Logging Settings
- `level`: Log level (DEBUG, INFO, WARNING, ERROR)
- `file`: Log file path
- `max_size_mb`: Maximum log file size in MB
- `backup_count`: Number of log file backups

### Sync Rules (`config/sync-rules.yaml`)

- `playlist_mappings`: Map MusicBee playlist names to DAP playlist names
- `path_transformations`: Path transformation rules
- `filters`: File filters (skip patterns, size limits)

## Usage

### Manual Sync

Run a sync manually:

```bash
docker-compose exec dap-sync python3 -m src.main --config /app/config/config.yaml
```

### Dry Run

Test configuration without syncing:

```bash
docker-compose exec dap-sync python3 -m src.main --config /app/config/config.yaml --dry-run
```

### Verbose Logging

Enable debug logging:

```bash
docker-compose exec dap-sync python3 -m src.main --config /app/config/config.yaml --verbose
```

### View Logs

```bash
# Container logs
docker-compose logs -f dap-sync

# Sync log file
tail -f logs/sync.log

# Cron log
tail -f logs/cron.log
```

## Sync Criteria Examples

### Sync Entire Library
```yaml
sync:
  criteria:
    - entire_library: true
```

### Sync Specific Playlists
```yaml
sync:
  criteria:
    - playlists: ["Favorites", "Workout", "Chill"]
```

### Sync High-Rated Tracks
```yaml
sync:
  criteria:
    - smart_playlists:
        - name: "High Rated"
          rating_min: 4
```

### Sync Recent Tracks
```yaml
sync:
  criteria:
    - smart_playlists:
        - name: "Recent"
          days: 30
```

### Sync by Genre
```yaml
sync:
  criteria:
    - custom:
        genres: ["Rock", "Jazz", "Classical"]
```

### Combined Criteria
```yaml
sync:
  criteria:
    - entire_library: true
    - playlists: ["Favorites"]
    - smart_playlists:
        - name: "Recent High Rated"
          rating_min: 4
          days: 30
```

## Troubleshooting

### ADB Connection Issues

**Problem**: Cannot connect to DAP
```
Solution:
1. Verify DAP IP address is correct
2. Ensure ADB over network is enabled on DAP
3. Check firewall settings on NAS
4. Try connecting manually: adb connect <IP>:5555
```

### File Path Issues

**Problem**: Files not found
```
Solution:
1. Verify MusicBee library paths in config.yaml
2. Check volume mounts in docker-compose.yml
3. Ensure paths use correct separators (Unix vs Windows)
4. Check file permissions on NAS
```

### Sync Not Running

**Problem**: Scheduled sync not executing
```
Solution:
1. Check cron is running: docker-compose exec dap-sync ps aux | grep cron
2. Verify schedule.enabled is true in config
3. Check cron logs: tail -f logs/cron.log
4. Verify container is running: docker-compose ps
```

### Metadata Not Preserved

**Problem**: Tags or artwork missing
```
Solution:
1. Verify metadata.preserve_tags is true
2. Check metadata.embed_artwork is true
3. Ensure source files have metadata
4. Check logs for metadata errors
```

### Playlist Issues

**Problem**: Playlists not syncing
```
Solution:
1. Verify playlist names match MusicBee playlist names
2. Check playlists_path in config
3. Ensure playlist files are .m3u or .m3u8 format
4. Check playlist tracks exist in library
```

## Project Structure

```
dap-sync/
├── Dockerfile                 # Docker image definition
├── docker-compose.yml         # Docker Compose configuration
├── requirements.txt           # Python dependencies
├── README.md                  # This file
├── config/
│   ├── config.yaml.example    # Configuration template
│   └── sync-rules.yaml.example # Sync rules template
├── src/
│   ├── main.py                # Main entry point
│   ├── dap_sync.py            # Sync engine
│   ├── musicbee_reader.py     # MusicBee library reader
│   ├── adb_client.py          # ADB client
│   ├── metadata_handler.py    # Metadata handler
│   └── playlist_handler.py    # Playlist handler
├── scripts/
│   └── entrypoint.sh          # Container entrypoint
├── logs/                       # Log files
└── data/                       # Sync database
```

## Development

### Running Locally (without Docker)

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Install ADB:
   ```bash
   # macOS
   brew install android-platform-tools
   
   # Linux
   sudo apt-get install android-tools-adb
   ```

3. Run sync:
   ```bash
   python3 -m src.main --config config/config.yaml
   ```

### Testing

Test individual components:

```bash
# Test ADB connection
docker-compose exec dap-sync adb devices

# Test MusicBee reader
docker-compose exec dap-sync python3 -c "from src.musicbee_reader import MusicBeeReader; ..."

# Dry run sync
docker-compose exec dap-sync python3 -m src.main --config /app/config/config.yaml --dry-run
```

## License

This project is provided as-is for personal use.

## Support

For issues or questions:
1. Check the troubleshooting section
2. Review logs in `logs/` directory
3. Verify configuration matches your setup
4. Check MusicBee library and DAP connectivity

## Notes

- First sync may take a long time depending on library size
- Incremental syncs are much faster
- Ensure DAP has sufficient storage space
- Network stability is important for large transfers
- Metadata operations may slow down sync for large libraries
