#!/bin/bash

# Start the Agent in the background
python agent.py start &

# Start the Web App (this stays in the foreground)
python main.py
