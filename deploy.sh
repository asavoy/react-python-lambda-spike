#!/bin/bash

set -eu
set -o pipefail

# Configuration
function_name="$(cd infrastructure && terraform output --json | jq -r .lambda_function_name.value)"
upload_bucket="$(cd infrastructure && terraform output --json | jq -r .upload_bucket.value)"
endpoint="$(cd infrastructure && terraform output --json | jq -r .endpoint.value)"
filename=lambda-function.zip

cyan='\033[0;36m'
green='\033[0;32m'
red='\033[0;31m'
nocolor='\033[0m'

echo -e "${cyan}Deploying to AWS Lambda...${nocolor}"

echo -e "${cyan}- Uploading ${filename} to s3://${upload_bucket}...${nocolor}"
aws s3 cp "$filename" "s3://${upload_bucket}/${filename}"

echo -e "${cyan}- Updating function code...${nocolor}"
response="$(aws lambda update-function-code \
  --function-name "$function_name" \
  --s3-bucket "$upload_bucket" \
  --s3-key "$filename" \
  --publish)"

status="$(echo "$response" | jq -r .LastUpdateStatus)"

echo
if [[ "$status" == "Successful" ]]; then
  echo -e "${green}✔ Deployment succeeded to ${endpoint}${nocolor}"
else
  echo -e "${red}✘ Deployment failed; status was ${status}${nocolor}"
  exit 1
fi
