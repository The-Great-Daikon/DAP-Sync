#!/bin/bash

# Entrypoint script for DAP sync container

set -e

# Default values
CONFIG_PATH=${CONFIG_PATH:-/app/config/config.yaml}
SYNC_RULES_PATH=${SYNC_RULES_PATH:-/app/config/sync-rules.yaml}
LOG_LEVEL=${LOG_LEVEL:-INFO}
DRY_RUN=${DRY_RUN:-false}

# Function to log messages
log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $1"
}

# Function to check if ADB is available
check_adb() {
    if ! command -v adb &> /dev/null; then
        log "ERROR: ADB not found. Please install android-tools-adb."
        exit 1
    fi
    log "ADB found: $(which adb)"
}

# Function to initialize ADB
init_adb() {
    log "Initializing ADB..."
    
    # Kill existing ADB server
    adb kill-server 2>/dev/null || true
    
    # Start ADB server
    adb start-server
    
    log "ADB server started"
}

# Function to check DAP connection
check_dap_connection() {
    log "Checking DAP connection..."
    
    # Read DAP IP and port from config
    if [ -f "$CONFIG_PATH" ]; then
        DAP_IP=$(grep -A 5 "dap:" "$CONFIG_PATH" | grep "ip_address:" | awk '{print $2}' | tr -d '"')
        DAP_PORT=$(grep -A 5 "dap:" "$CONFIG_PATH" | grep "port:" | awk '{print $2}' | tr -d '"' || echo "5555")
    fi
    
    if [ -z "$DAP_IP" ]; then
        log "WARNING: DAP IP address not found in config. Connection check skipped."
        return 0
    fi
    
    log "Attempting to connect to DAP at $DAP_IP:$DAP_PORT..."
    
    # Try to connect
    if adb connect "$DAP_IP:$DAP_PORT" 2>&1 | grep -q "connected"; then
        log "Successfully connected to DAP at $DAP_IP:$DAP_PORT"
        
        # Check if device is online
        if adb devices | grep -q "$DAP_IP:$DAP_PORT.*device$"; then
            log "DAP is online and ready"
            return 0
        else
            log "WARNING: DAP is connected but not online"
            return 1
        fi
    else
        log "WARNING: Could not connect to DAP at $DAP_IP:$DAP_PORT"
        log "Make sure ADB over network is enabled on the DAP"
        return 1
    fi
}

# Function to setup cron job
setup_cron() {
    log "Setting up cron job..."
    
    # Read schedule from config
    if [ -f "$CONFIG_PATH" ]; then
        SCHEDULE_ENABLED=$(grep -A 5 "schedule:" "$CONFIG_PATH" | grep "enabled:" | awk '{print $2}' | tr -d '"' || echo "true")
        SCHEDULE_TIME=$(grep -A 5 "schedule:" "$CONFIG_PATH" | grep "time:" | awk '{print $2}' | tr -d '"' || echo "02:00")
    else
        SCHEDULE_ENABLED="true"
        SCHEDULE_TIME="02:00"
    fi
    
    if [ "$SCHEDULE_ENABLED" != "true" ]; then
        log "Scheduling is disabled in config"
        return 0
    fi
    
    # Parse time (HH:MM)
    SCHEDULE_HOUR=$(echo "$SCHEDULE_TIME" | cut -d: -f1)
    SCHEDULE_MINUTE=$(echo "$SCHEDULE_TIME" | cut -d: -f2)
    
    # Create cron job
    CRON_JOB="$SCHEDULE_MINUTE $SCHEDULE_HOUR * * * cd /app && python3 -m src.main --config $CONFIG_PATH --sync-rules $SYNC_RULES_PATH >> /logs/cron.log 2>&1"
    
    # Add to crontab
    echo "$CRON_JOB" | crontab -
    
    log "Cron job scheduled for daily sync at $SCHEDULE_TIME"
    log "Cron job: $CRON_JOB"
}

# Function to run sync
run_sync() {
    log "Running sync..."
    
    # Build command
    CMD="python3 -m src.main --config $CONFIG_PATH --sync-rules $SYNC_RULES_PATH"
    
    if [ "$DRY_RUN" = "true" ]; then
        CMD="$CMD --dry-run"
    fi
    
    if [ "$LOG_LEVEL" = "DEBUG" ]; then
        CMD="$CMD --verbose"
    fi
    
    # Run sync
    eval "$CMD"
    
    SYNC_EXIT_CODE=$?
    
    if [ $SYNC_EXIT_CODE -eq 0 ]; then
        log "Sync completed successfully"
    else
        log "Sync failed with exit code $SYNC_EXIT_CODE"
    fi
    
    return $SYNC_EXIT_CODE
}

# Function to keep container running
keep_running() {
    log "Container will keep running for scheduled syncs"
    log "Cron daemon starting..."
    
    # Start cron daemon
    cron
    
    # Keep container running
    while true; do
        sleep 3600  # Sleep for 1 hour
        log "Container is running... (sleeping)"
    done
}

# Main execution
main() {
    log "Starting DAP sync container..."
    log "Configuration: $CONFIG_PATH"
    log "Sync rules: $SYNC_RULES_PATH"
    log "Log level: $LOG_LEVEL"
    log "Dry run: $DRY_RUN"
    
    # Check ADB
    check_adb
    
    # Initialize ADB
    init_adb
    
    # Check DAP connection (non-blocking)
    check_dap_connection || log "WARNING: DAP connection check failed. Sync may fail."
    
    # Setup cron if scheduling is enabled
    setup_cron
    
    # Run initial sync if requested
    if [ "$INITIAL_SYNC" = "true" ]; then
        log "Running initial sync..."
        run_sync
    fi
    
    # Check if we should keep running
    if [ "$KEEP_RUNNING" = "true" ] || [ "$SCHEDULE_ENABLED" = "true" ]; then
        keep_running
    else
        log "Container will exit after sync"
        exit 0
    fi
}

# Run main function
main "$@"

