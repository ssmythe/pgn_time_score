#!/bin/bash
# process_pgns.sh
# Usage: ./process_pgns.sh /path/to/root_directory
#
# This script recursively searches the given directory for PGN files
# that have a filename ending with "_movetimes.pgn". It then calls the
# Python script pgn_time_score.py for each file, outputting the report to
# the same directory but with the filename ending changed to "_clock.txt".

# Check if a root directory was provided.
if [ "$#" -ne 1 ]; then
    echo "Usage: $0 /path/to/root_directory"
    exit 1
fi

ROOT_DIR="$1"

# Verify that the provided directory exists.
if [ ! -d "$ROOT_DIR" ]; then
    echo "Error: Directory '$ROOT_DIR' does not exist."
    exit 1
fi

# Loop through each file ending with _movetimes.pgn.
find "$ROOT_DIR" -type f -name "*_movetimes.pgn" | while read -r PGN_FILE; do
    # Extract directory and basename.
    DIR=$(dirname "$PGN_FILE")
    BASE=$(basename "$PGN_FILE")
    # Remove the '_movetimes.pgn' suffix and append '_clock.txt'.
    PREFIX="${BASE%_movetimes.pgn}"
    OUTPUT_FILE="$DIR/${PREFIX}_clock.txt"
    
    echo "Processing '$PGN_FILE' -> '$OUTPUT_FILE'"
    
    # Call the Python script.
    python3 pgn_time_score.py -i "$PGN_FILE" -o "$OUTPUT_FILE"
    
    # Check if the Python script succeeded.
    if [ $? -ne 0 ]; then
        echo "Error processing '$PGN_FILE'"
    fi
done
