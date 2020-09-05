#!/bin/bash

set -euo pipefail

out=bootstrap.zip

rm -f "$out"

# Fix permissions for AWS Lambda
chmod 644 *.py

zip "$out" *.py
