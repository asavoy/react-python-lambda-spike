# react-python-lambda-spike

Run a React + Python web application on AWS Lambda

## Setup

```bash
(cd api && mkvenv $(cat .python-version) && pip install -r api/requirements.txt)
(cd app && yarn install)
(cd infrastructure && terraform init)
```

## Use cases

Run Python API server locally:

```bash
cd api
python app.py
```

Test the Python API server running locally:

```bash
curl http://localhost:8000/api/date
# {"date": "2020-09-05T17:06:29.287091"}
```

Run React client web application locally:

```bash
cd app
yarn start
```

Test the React client webvapplication locally:

- Visit http://localhost:3000/
- The page should display, but will fail to fetch the date from the Python server

Run the proxy server locally:

```bash
# The proxy server runs the Python API server and also serves the web application
(cd app; yarn build)
python proxy.py
```

Test the proxy server locally:

- Visit http://localhost:8000/
- The page should should display, and fetch the date from the Python server

Deploy infrastructure:

```bash
cd infrastructure
terraform apply
```

Deploy the system:

```bash
./build.sh
# Created lambda-function.zip

./deploy.sh
# Deployment succeeded to https://wqdafv7axb.execute-api.us-west-2.amazonaws.com
```

Test the deployed system:

- Visit the URL emitted by the deployment script
- The page should should display, and fetch the date from the Python server
