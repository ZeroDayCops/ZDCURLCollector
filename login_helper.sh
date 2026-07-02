#!/bin/bash
# Change directory to the script's actual directory so it runs correctly from anywhere
cd "$(dirname "$(readlink -f "$0")")"

# If no platform argument is provided, show usage
if [ -z "$1" ]; then
    echo "Usage: $0 <platform>"
    echo "Supported platforms: instagram, facebook, linkedin, pinterest"
    exit 1
fi

# Run login_helper using the virtual environment python
./venv/bin/python -m app.tools.login_helper "$@"
