"""HubWise shared Python library for Azure Functions automation.

Modules: config (fail-loud env loading), guards (DRY_RUN/ALLOW_PROD write
gate), http (retrying requests session), logging (structured summary lines
+ alert markers + secret redaction), state (Table Storage idempotency).
"""

__version__ = "0.2.1"
