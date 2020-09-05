#!/bin/bash

set -eu
set -o pipefail

# Configuration
filename=lambda-function.zip
runtime=python3.8
api_source_path=api
static_path=app/build

cyan='\033[0;36m'
green='\033[0;32m'
nocolor='\033[0m'

echo -e "${cyan}Building AWS Lambda package...${nocolor}"

# Convert to absolute paths
filepath="$(cd "$(dirname "$filename")"; pwd)/$(basename "$filename")"
api_source_abspath="$(cd "$api_source_path"; pwd)"
static_abspath="$(cd "$static_path"; pwd)"

# Setup a temporary path for the build
temp_build_path=$(mktemp -d "/tmp/build-lambda.XXXXXXXXX")
trap "{ rm -rf '$temp_build_path'; }" EXIT

# Build web application
echo -e "${cyan}- Building JavaScript web application...${nocolor}"
(cd "app" && yarn install && yarn build)

# Copy proxy
echo -e "${cyan}- Copying proxy...${nocolor}"
cp proxy.py "${temp_build_path}/"

# Copy Python API server code
echo -e "${cyan}- Copying /${api_source_path}...${nocolor}"
mkdir -p "${temp_build_path}/${api_source_path}"
cp -R "$api_source_abspath" "$(dirname "${temp_build_path}/${api_source_path}")"

# Copy static files for web application
echo -e "${cyan}- Copying /${static_path}...${nocolor}"
mkdir -p "${temp_build_path}/${static_path}"
cp -R "$static_abspath" "$(dirname "${temp_build_path}/${static_path}")"

# Install dependencies, using a Docker image to correctly build native extensions
echo -e "${cyan}- Installing Python dependencies...${nocolor}"
docker run --rm -t -v "$temp_build_path:/code" -w /code lambci/lambda:build-$runtime \
    sh -c "
cd /code
mkdir .pypath
pip install -r ${api_source_path}/requirements.txt -t .pypath/
"

# Fix permissions for use on AWS Lambda
echo -e "${cyan}- Fixing permissions...${nocolor}"
find "$temp_build_path" -type f -exec chmod 644 {} \;
find "$temp_build_path" -type d  -exec chmod 755 {} \;

# Cleanup old build output
[ -f "$filepath" ] && rm "$filepath"

# Build zip package with files at root
echo -e "${cyan}- Creating zip file...${nocolor}"
(cd "$temp_build_path"; zip --recurse-patterns "$filepath" "*" --exclude "*.pyc" --exclude "*.map")

echo
echo -e "${green}✔ Created $filepath from $api_source_abspath${nocolor}"
echo
