#!/bin/bash
# Change directory to the script's actual directory so it runs correctly from anywhere
cd "$(dirname "$(readlink -f "$0")")"

# Run check_sessions using the virtual environment python
./venv/bin/python -m app.tools.check_sessions "$@"
