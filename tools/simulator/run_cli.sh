#!/bin/bash
# This script sets up a virtual environment and runs the simulator CLI.

# Change to the script's directory
cd "$(dirname "$0")" || { echo "Failed to change directory."; exit 1; }

VENV_DIR="venv"

# Check if the virtual environment exists
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
    if [ $? -ne 0 ]; then
        echo "Failed to create virtual environment. Please make sure python3 and venv are installed."
        exit 1
    fi
fi

# Activate the virtual environment and install dependencies
source "$VENV_DIR/bin/activate"

# Only install dependencies if requirements have changed to speed up startup.
REQUIREMENTS_HASH_FILE="$VENV_DIR/.requirements_hash"
CURRENT_HASH=$(shasum -a 256 requirements.txt | awk '{print $1}')

if [ ! -f "$REQUIREMENTS_HASH_FILE" ] || [ "$(cat "$REQUIREMENTS_HASH_FILE")" != "$CURRENT_HASH" ]; then
    echo "Installing dependencies from requirements.txt..."
    pip3 install -q -r requirements.txt
    echo "$CURRENT_HASH" > "$REQUIREMENTS_HASH_FILE"
fi

# Run the application with any forwarded arguments
echo "Starting Simulator CLI..."
python3 simulator_cli.py "$@"

# Deactivate the virtual environment
deactivate