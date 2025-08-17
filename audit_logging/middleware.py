import time
import logging
import json
import re
import contextlib

from asgiref.local import Local
from asgiref.sync import iscoroutinefunction, markcoroutinefunction
from django.http import HttpResponse
from django.utils.deprecation import MiddlewareMixin

from .settings import UNREGISTERED_URLS, REGISTERED_URLS
from .constants import REQUEST_TYPES

logger = logging.getLogger("audit.request")

_thread_locals = Local()


class MockRequest:
    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)
        self.user = user
        super().__init__(*args, **kwargs)


def get_current_request():
    return getattr(_thread_locals, "request", None)


def set_current_request(request):
    _thread_locals.request = request


def get_current_user():
    request = get_current_request()
    if request:
        return getattr(request, "user", None)
    return None


def set_current_user(user):
    try:
        _thread_locals.request.user = user
    except AttributeError:
        request = MockRequest(user=user)
        _thread_locals.request = request


def clear_request():
    with contextlib.suppress(AttributeError):
        del _thread_locals.request


def should_log_url(url):
    # check if current url is blacklisted
    for unregistered_url in UNREGISTERED_URLS:
        pattern = re.compile(unregistered_url)
        if pattern.match(url):
            return False

    # only audit URLs listed in REGISTERED_URLS (if it's set)
    if len(REGISTERED_URLS) > 0:
        for registered_url in REGISTERED_URLS:
            pattern = re.compile(registered_url)
            if pattern.match(url):
                return True
        return False

    # all good
    return True


class AuditLoggingMiddleware(MiddlewareMixin):
    """
    log structure:
    {
        "timestamp": "2021-01-01 12:00:00.000",
        "level": "INFO",
        "name": "audit.request",
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

    def __init__(self, get_response):
        self.get_response = get_response
        self.log_data = {
            "service_name": "review_board",
            "request_type": REQUEST_TYPES[0],
            "protocol": None,
            "request_repr": {},
            "response_repr": {},
            "error_message": None,
            "execution_time": 0,
        }

        if iscoroutinefunction(self.get_response):
            markcoroutinefunction(self)

    def __call__(self, request):
        if iscoroutinefunction(self):
            return self.__acall__(request)
        set_current_request(request)

        if not should_log_url(request.path):
            return self.get_response(request)

        start_time = time.time()

        # Log request
        request_data = {
            "method": request.method,
            "path": request.path,
            "query_params": dict(request.GET.items()),
            "headers": dict(request.headers),
            "user": str(request.user) if request.user.is_authenticated else None,
        }

        if request.content_type == "application/json":
            try:
                body = json.loads(request.body)
                request_data["body"] = body
            except json.JSONDecodeError:
                request_data["body"] = "Invalid JSON"

        # Get response
        response = self.get_response(request)
        end_time = time.time()

        # TODO: Find way to add status code to response_data

        # Log response
        response_data = {
            "headers": dict(response.headers),
        }

        if isinstance(response, HttpResponse):
            try:
                content = response.content.decode("utf-8")
                if content:
                    try:
                        response_data["body"] = json.loads(content)
                    except json.JSONDecodeError:
                        response_data["body"] = content
            except UnicodeDecodeError:
                response_data["body"] = "Binary content"

        self.log_data["execution_time"] = end_time - start_time
        self.log_data["protocol"] = "https" if request.is_secure() else "http"
        self.log_data["request_repr"] = request_data
        self.log_data["response_repr"] = response_data

        logger.api("Audit Internal Request", extra=self.log_data)

        clear_request()

        return response

    async def __acall__(self, request):
        set_current_request(request)

        if not should_log_url(request.path):
            return await self.get_response(request)

        start_time = time.time()

        # Log request
        request_data = {
            "method": request.method,
            "path": request.path,
            "query_params": dict(request.GET.items()),
            "headers": dict(request.headers),
            "user": str(request.user) if request.user.is_authenticated else None,
        }

        if request.content_type == "application/json":
            try:
                body = json.loads(request.body)
                request_data["body"] = body
            except json.JSONDecodeError:
                request_data["body"] = "Invalid JSON"

        # Get response
        response = await self.get_response(request)
        end_time = time.time()

        # TODO: Find way to add status code to response_data

        # Log response
        response_data = {
            "headers": dict(response.headers),
        }

        if isinstance(response, HttpResponse):
            try:
                content = response.content.decode("utf-8")
                if content:
                    try:
                        response_data["body"] = json.loads(content)
                    except json.JSONDecodeError:
                        response_data["body"] = content
            except UnicodeDecodeError:
                response_data["body"] = "Binary content"

        self.log_data["execution_time"] = end_time - start_time
        self.log_data["protocol"] = "https" if request.is_secure() else "http"
        self.log_data["request_repr"] = request_data
        self.log_data["response_repr"] = response_data

        logger.api("Audit Internal Request", extra=self.log_data)

        clear_request()

        return response
