"""
proxy.py is a shim to run a Python API server and JavaScript web application on an AWS Lambda Function.

The Python API server:
- must run with the command `python api/app.py` or set by API_COMMAND
- must run a web server listening to requests on the port provided in the PORT env var
- should expect to receive requests on the `/api` path only
- must have its dependencies installed to .pypath/ using `pip install -r requirements.txt -t .pypath/`

The JavaScript web application:
- must consist of static files only, such as *.html, *.js, *.css; i.e. output of Webpack builds
- must have the static files located at `app/build/` or as set by STATIC_PATH
- must provide `/index.html` which will be served at the root path `/`
- may make requests to the API server at the host-relative path `/api`

Known issues / areas of improvement:
- if the API server process terminates, there is no polling to detect this or restart it
- doesn't pass through all context data, such as source IP
- no caching implemented, such as support for Expires, If-Modified-Since, If-Match
- better handling of failure scenarios, such as timeouts and server errors
- handling of CORS headers
- development mode to pass requests to Python and Webpack dev servers
"""
import base64
import os
import socket
import subprocess
import time
from email.message import Message
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, HTTPServer
from mimetypes import guess_type
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlencode, urlparse


# Command to start the API server, which must listen on the port specified in
# the PORT environment variable it is provided
API_COMMAND = os.environ.get("API_COMMAND", "python api/app.py")

# Time to wait for API server to start, in seconds
API_START_TIMEOUT = int(os.environ.get("API_START_TIMEOUT", 5))

# Location of the static files to be served, should be the output from
# the production build of the web application
STATIC_PATH = os.environ.get("STATIC_PATH", "app/build")

# Port for the proxy server to listen on, when running as a local web server
PROXY_PORT = int(os.environ.get("PORT", 8000))

# Path
PATH = os.environ.get("PATH", "")


def one_time_init():
    """One-time initialisation, of API server process and proxy application"""
    api_server_host, api_server_port = "localhost", 8180
    one_time_init.api_process = start_api_server_process(
        command=API_COMMAND,
        host=api_server_host,
        port=api_server_port,
        start_timeout=API_START_TIMEOUT,
        path=PATH,
    )
    one_time_init.proxy_app = make_proxy_app(
        static_path=STATIC_PATH,
        api_server_host=api_server_host,
        api_server_port=api_server_port,
    )


def lambda_handler(event, context) -> Dict:
    """Entrypoint for use in AWS Lambda and API Gateway HTTP APIs"""
    # Parse the request from an API Gateway 2.0 event
    assert event["version"] == "2.0"
    method = event["requestContext"]["http"]["method"]
    path = event["requestContext"]["http"]["path"]
    query_string = event["rawQueryString"] or ""
    query = parse_qs(query_string)
    headers = {name: values.split(",") for name, values in event["headers"].items()}
    for cookie in event.get("cookies", []):
        if "Cookie" in headers:
            headers["Cookie"].append(cookie)
        else:
            headers["Cookie"] = [cookie]
    body = event.get("body", "")
    if event["isBase64Encoded"]:
        body = base64.standard_b64decode(body)

    # Calculate timeout based on AWS Lambda execution time limit
    timeout_buffer = 1  # in seconds
    timeout = context.get_remaining_time_in_millis() / 1000 - timeout_buffer

    # Route the request to the appropriate handler
    status, response_headers, response_body = one_time_init.proxy_app(
        method=method,
        path=path,
        query=query,
        headers=headers,
        body=body,
        timeout=timeout,
    )

    # Encode the response for API Gateway 2.0
    if _is_binary_content(response_headers):
        is_base64_encoded = True
        response_body = base64.standard_b64encode(response_body)
    else:
        is_base64_encoded = False
    return {
        "statusCode": status,
        "headers": {
            name: ",".join(values)
            for name, values in response_headers.items()
            if name.lower() != "set-cookie"
        },
        "cookies": [
            cookie
            for name, values in response_headers.items()
            if name.lower() == "set-cookie"
            for cookie in values
        ],
        "isBase64Encoded": is_base64_encoded,
        "body": response_body,
    }


def main():
    """Entrypoint for use as local web server, for testing purposes"""
    proxy_host, proxy_port = "", PROXY_PORT

    class RequestHandler(BaseHTTPRequestHandler):
        def do_request(self):
            try:
                # Parse the HTTP request
                method = self.command
                _, _, path, _, query_string, _ = urlparse(self.path)
                query = parse_qs(query_string)
                headers = {}
                for name, value in self.headers.items():
                    if name in headers:
                        headers[name].append(value)
                    else:
                        headers[name] = [value]
                length = int(self.headers.get("Content-Length", 0))
                if length:
                    body = self.rfile.read(length)
                else:
                    body = None
                timeout = 15

                # Route the request to the appropriate handler
                status, response_headers, response_body = one_time_init.proxy_app(
                    method=method,
                    path=path,
                    query=query,
                    headers=headers,
                    body=body,
                    timeout=timeout,
                )

                # Send as an HTTP response
                self.send_response(status)
                for name, values in response_headers.items():
                    for value in values:
                        self.send_header(name, value)
                self.end_headers()
                if response_body:
                    self.wfile.write(response_body)
            except Exception as e:
                self.send_error(500, "Internal Server Error")
                raise e

        do_DELETE = do_request
        do_GET = do_request
        do_HEAD = do_request
        do_OPTIONS = do_request
        do_POST = do_request
        do_PUT = do_request

    httpd = HTTPServer((proxy_host, proxy_port), RequestHandler)

    print(f"Proxy server running at {proxy_host}:{proxy_port} ...")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("Terminating...")
        one_time_init.api_process.terminate()


def start_api_server_process(
    command: str, host: str, port: int, start_timeout: int, path: str
) -> subprocess.Popen:
    print(f"Starting API server on {host}:{port} ...")
    process = subprocess.Popen(
        command,
        shell=True,
        env={"PATH": path, "PORT": str(port), "PYTHONPATH": ".pypath/"},
        stdin=None,
        text=True,
    )
    end_time = time.monotonic() + start_timeout
    while True:
        time.sleep(0.01)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # Check if port is open
        if sock.connect_ex((host, port)) == 0:
            break
        if time.monotonic() >= end_time:
            process.terminate()
            raise RuntimeError("Timeout waiting for API server to start")
    print(f"API server started")
    return process


def make_proxy_app(
    static_path: str, api_server_host: str, api_server_port: int
) -> Callable:
    """Builds the proxy server application and returns the root request handler"""

    def _root_handler(
        method: str,
        path: str,
        query: Dict[str, List[str]],
        headers: Dict[str, List[str]],
        body: Optional[bytes],
        timeout: float,
    ) -> Tuple[int, Dict[str, List[str]], Optional[bytes]]:
        """Root request handler"""
        if path == "/":
            return _static_handler(method=method, path="/index.html")
        elif path.startswith("/api/"):
            return _api_server_handler(
                method=method,
                path=path,
                query=query,
                headers=headers,
                body=body,
                timeout=timeout,
            )
        else:
            return _static_handler(method=method, path=path)

    def _api_server_handler(
        method: str,
        path: str,
        query: Dict[str, List[str]],
        headers: Dict[str, List[str]],
        body: Optional[bytes],
        timeout: float,
    ) -> Tuple[int, Dict[str, List[str]], Optional[bytes]]:
        """Resolves requests by proxying to the API server"""
        url = path
        if len(query):
            url += "?" + urlencode(query, doseq=True)
        # Build a dict-like that supports multiple values per key
        headers_multi = Message()
        for name, values in headers.items():
            for value in values:
                headers_multi.add_header(name, value)

        connection = HTTPConnection(api_server_host, api_server_port, timeout=timeout)
        connection.request(
            method=method, url=url, headers=headers_multi, body=body,
        )
        response = connection.getresponse()

        status = response.status
        response_headers = {}
        for name, value in response.getheaders():
            if name in response_headers:
                response_headers[name].append(value)
            else:
                response_headers[name] = [value]
        response_body = response.read()
        return status, response_headers, response_body

    def _static_handler(
        method: str, path: str
    ) -> Tuple[int, Dict[str, List[str]], Optional[bytes]]:
        """Resolves requests by returning matching files in `static_path`"""
        method = method.upper()
        filepath = Path(static_path) / path.lstrip("/")
        accepted_methods = ("GET", "HEAD")
        if method in accepted_methods and filepath.exists() and filepath.is_file():
            if method == "HEAD":
                response_body = b""
                content_length = filepath.stat().st_size
            else:
                response_body = filepath.read_bytes()
                content_length = len(response_body)
            guessed_type = guess_type(path)[0]
            content_type = guessed_type or "text/plain"
            return (
                200,
                {
                    "Content-Length": [str(content_length)],
                    "Content-Type": [content_type],
                },
                response_body,
            )
        elif method not in accepted_methods:
            response_body = b"Bad Request"
            return (
                401,
                {
                    "Content-Length": [str(len(response_body))],
                    "Content-Type": ["text/plain"],
                },
                response_body,
            )
        else:
            response_body = b"Not Found"
            return (
                404,
                {
                    "Content-Length": [str(len(response_body))],
                    "Content-Type": ["text/plain"],
                },
                response_body,
            )

    return _root_handler


def _is_binary_content(headers: Dict[str, List[str]]) -> bool:
    """Returns True if the headers indicate binary content"""
    content_type = "text/plain"
    content_encoding = "identity"
    for name, values in headers.items():
        if name.lower() == "content-type":
            content_type = values[0]
        if name.lower() == "content-encoding":
            content_encoding = values[0]
    if content_encoding != "identity":
        return True
    if _is_text_content_type(content_type):
        return False
    return True


def _is_text_content_type(content_type: str) -> bool:
    """Returns True if the Content-Type value indicates text content"""
    if content_type.startswith("text/"):
        return True
    elif content_type.startswith("application/javascript"):
        return True
    elif content_type.startswith("application/json"):
        return True
    elif content_type.startswith("image/svg+xml"):
        return True
    return False


one_time_init()

if __name__ == "__main__":
    main()
