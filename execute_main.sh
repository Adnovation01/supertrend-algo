#!/bin/bash

# Create virtual environment
echo "Creating virtual environment."
python3 -m venv venv_sh

# Activate virtual environment
echo "Activating virtual environment."
source venv_sh/bin/activate

# Install Python packages
echo "Installing Python packages."
python3 -m pip install -r requirements_sh.txt
echo "Python packages installed."

# Start Flask backend server
echo "Starting Flask backend server."
python3 main.py