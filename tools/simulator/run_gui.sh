#!/bin/bash
# This script sets up a virtual environment and runs the PyQt simulator GUI.

# Change to the script's directory
cd "$(dirname "$0")"

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
echo "Installing dependencies from requirements.txt..."
pip3 install -r requirements.txt

# Run the application
echo "Starting PyQt Simulator GUI..."
python3 simulator_gui.py

# Deactivate the virtual environment
deactivate