import logging

AUDIT = 21
API = 22
LOGIN = 23

# Only add the level if it doesn't already exist
if not hasattr(logging, "AUDIT"):
    logging.addLevelName(AUDIT, "AUDIT")

    # Add the audit method to Logger class
    def audit(self, message, *args, **kwargs):
        if self.isEnabledFor(AUDIT):
            self._log(AUDIT, message, args, **kwargs)

    logging.Logger.audit = audit
else:
    # Use existing AUDIT level if it's already defined
    AUDIT = logging.AUDIT

if not hasattr(logging, "API"):
    logging.addLevelName(API, "API")

    def api(self, message, *args, **kwargs):
        if self.isEnabledFor(API):
            self._log(API, message, args, **kwargs)

    logging.Logger.api = api
else:
    API = logging.API

if not hasattr(logging, "LOGIN"):
    logging.addLevelName(LOGIN, "LOGIN")

    def login(self, message, *args, **kwargs):
        if self.isEnabledFor(LOGIN):
            self._log(LOGIN, message, args, **kwargs)

    logging.Logger.login = login
else:
    LOGIN = logging.LOGIN
