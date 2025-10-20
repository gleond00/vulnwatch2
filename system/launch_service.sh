#!/bin/bash

# Usageo: ...geah/> system/launch_service "python ./hl7_app/hl7service.py"

# Function to execute the command repeatedly
execute_command() {
    command="$1"  # Command to execute
    interval="$2" # Time interval between executions in seconds

    while true; do
	    echo "Relaunch service"
        $command  # Execute the command
        sleep "$interval"  # Wait for the specified interval
    done
}

# Call the function with your desired command and interval (in seconds)
execute_command $1 5  # Replace "YOUR_COMMAND_HERE" with the actual command you want to execute
