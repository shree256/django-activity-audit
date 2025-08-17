import time
import paramiko
import logging

from typing import Tuple, Optional
from requests.sessions import Session

from .constants import REQUEST_TYPES

logger = logging.getLogger("easy.request")

PROTOCOLS = ("http", "sftp")
OPERATIONS = ("upload", "download")
THIRTY_SECONDS_TIMEOUT = 30

"""
    log structure:
    {
        "timestamp": "2021-01-01 12:00:00.000",
        "level": "INFO",
        "name": "audit.request",
        "request_type": "external",
        "service_name": "default",
        "protocol": "http",
        "request_repr": {
            "endpoint": "https://example.com/api/v1/users",
            "method": "GET",
            "headers": {"Content-Type": "application/json"},
            "body": {"name": "John Doe", "email": "john.doe@example.com"},
        },
        "response_repr": {
            "status_code": 200,
            "body": {"name": "John Doe", "email": "john.doe@example.com"},
        },
        "error_message": "",
        "execution_time": 0,
    }
"""


class HTTPClient(Session):
    def __init__(self, service_name: str = "default"):
        super().__init__()
        self.log_payload = {
            "service_name": service_name,
            "protocol": PROTOCOLS[0],
            "request_type": REQUEST_TYPES[1],
            "request_repr": {},
            "response_repr": {},
            "error_message": "",
            "execution_time": 0,
        }

    def request(self, method, url, **kwargs):
        start_time = time.time()
        headers = kwargs.get("headers", {})
        data = kwargs.get("data", {})
        error = None
        response = None

        request_repr = {
            "endpoint": url,
            "method": method,
            "headers": headers,
            "body": data,
        }

        try:
            response = super().request(method, url, **kwargs)
            response_repr = {
                "status_code": response.status_code,
                "body": response.json(),
            }
        except Exception as e:
            error = str(e)

        execution_time = time.time() - start_time

        self.log_payload["request_repr"] = str(request_repr)
        self.log_payload["execution_time"] = execution_time

        if error:
            self.log_payload["error_message"] = error
        else:
            self.log_payload["response_repr"] = str(response_repr)

        logger.api("Audit External Service", extra=self.log_payload)

        return response


class SFTPClient:
    def __init__(
        self,
        host,
        port,
        username,
        password,
        service_name,
    ):
        self.client = paramiko.SSHClient()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.service_name = service_name
        self.channel = None
        self.log_payload = {
            "service_name": service_name,
            "request_type": REQUEST_TYPES[1],
            "protocol": PROTOCOLS[1],
            "request_repr": {
                "host": host,
                "operation": None,
                "remote_path": None,
                "filename": None,
            },
            "response_repr": None,
            "error_message": None,
            "execution_time": 0,
        }

    def __create_log(self):
        # Add external service log
        pass

    def connect(
        self,
    ) -> Tuple[Optional[paramiko.SFTPClient], Optional[Exception]]:
        try:
            if not self.channel:
                self.client.connect(
                    self.host,
                    self.port,
                    self.username,
                    self.password,
                    timeout=THIRTY_SECONDS_TIMEOUT,
                )
                self.channel = self.client.open_sftp()
                logger.info("SFTP connection established successfully")
            logger.info("Reusing existing SFTP connection")
        except Exception as e:
            error_message = f"SFTP connection failed. Error: {str(e)}"
            logger.info(error_message)
            self.log_payload["error_message"] = error_message
            self.__create_log()
            return None, e

        return self.channel, None

    def is_valid_path(self, path_to_folder) -> Tuple[bool, Optional[str]]:
        if self.channel:
            try:
                self.channel.listdir(path_to_folder)
                logger.info(f"{path_to_folder} validated successfully")
                return True, None
            except Exception as _:
                return False, f"Folder({path_to_folder}) not found."
        return False, f"Connection not established"

    def upload(
        self, path_to_folder, filename, file_content
    ) -> Tuple[bool, Optional[str]]:
        start_time = time.time()
        result = ""

        self.log_payload["request_repr"]["operation"] = OPERATIONS[0]
        self.log_payload["request_repr"]["remote_path"] = path_to_folder
        self.log_payload["request_repr"]["filename"] = filename

        if self.channel:
            _, error = self.is_valid_path(path_to_folder)

            if not error:
                try:
                    with self.channel.open(
                        f"{path_to_folder}{filename}", "wb"
                    ) as remote_file:
                        remote_file.write(file_content)
                    result = f"{filename} uploaded successfully to {path_to_folder}"
                    logger.info(f"{result}")
                except Exception as e:
                    self.log_payload[
                        "error_message"
                    ] = f"File upload failed. Error: {str(e)}"
            self.log_payload[
                "error_message"
            ] = f"Path validation failed. Error: {str(error)}"
        else:
            self.log_payload["error_message"] = "Connection not established"

        execution_time = time.time() - start_time

        self.log_payload["response_repr"] = {"message": result}
        self.log_payload["execution_time"] = execution_time

        self.__create_log()

        return result

    def close(self):
        if self.channel:
            self.channel.close()
        self.client.close()
