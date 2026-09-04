#!/bin/bash

set -e

echo "Initializing ClimateCube database..."

mkdir -p data

rm -f data/climatecube.db

sqlite3 data/climatecube.db < db/create_database.sql
sqlite3 data/climatecube.db < db/seed_data.sql

echo "Database initialized."
