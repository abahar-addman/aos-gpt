import json
import logging
import sys
from typing import TYPE_CHECKING

from loguru import logger
from opentelemetry import trace
from open_webui.env import (
    ENABLE_AUDIT_STDOUT,
    ENABLE_AUDIT_LOGS_FILE,
    AUDIT_LOGS_FILE_PATH,
    AUDIT_LOG_FILE_ROTATION_SIZE,
    AUDIT_LOG_LEVEL,
    GLOBAL_LOG_LEVEL,
    AUDIT_UVICORN_LOGGER_NAMES,
    ENABLE_OTEL,
    ENABLE_OTEL_LOGS,
    LOG_FORMAT,
    DD_SERVICE,
    DD_ENV,
)

if TYPE_CHECKING:
    from loguru import Record


def stdout_format(record: "Record") -> str:
    """
    Generates a formatted string for log records that are output to the console. This format includes a timestamp, log level, source location (module, function, and line), the log message, and any extra data (serialized as JSON).

    Parameters:
    record (Record): A Loguru record that contains logging details including time, level, name, function, line, message, and any extra context.
    Returns:
    str: A formatted log string intended for stdout.
    """
    if record["extra"]:
        record["extra"]["extra_json"] = json.dumps(record["extra"])
        extra_format = " - {extra[extra_json]}"
    else:
        extra_format = ""
    return (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
        "<level>{message}</level>" + extra_format + "\n{exception}"
    )


def stdout_json_sink(message) -> None:
    """
    Loguru sink that emits one JSON object per line to stdout for Datadog ingestion.

    Datadog parses JSON stdout natively and surfaces top-level keys as facets. We
    keep the standard `level`/`logger`/`message` keys, flatten Datadog's reserved
    `dd.trace_id`/`dd.span_id` so log-trace correlation works, and stamp the
    Unified Service Tagging fields on every line.
    """
    record = message.record
    payload = {
        "timestamp": record["time"].isoformat(),
        "level": record["level"].name,
        "logger": record["name"],
        "function": record["function"],
        "line": record["line"],
        "message": record["message"],
        "service": DD_SERVICE,
        "env": DD_ENV,
    }

    extra = dict(record["extra"])
    # Datadog's reserved correlation keys are dotted; lift them to the top level
    # rather than nesting inside "extra" so the UI auto-links logs to traces.
    for dd_key in ("dd.trace_id", "dd.span_id"):
        if dd_key in extra:
            payload[dd_key] = extra.pop(dd_key)
    if extra:
        payload["extra"] = extra

    if record["exception"] is not None:
        exc = record["exception"]
        payload["error"] = {
            "kind": exc.type.__name__ if exc.type else None,
            "message": str(exc.value) if exc.value else None,
            "stack": message,  # loguru renders traceback into the formatted message
        }

    print(json.dumps(payload, default=str), file=sys.stdout, flush=True)


class InterceptHandler(logging.Handler):
    """
    Intercepts log records from Python's standard logging module
    and redirects them to Loguru's logger.
    """

    def emit(self, record):
        """
        Called by the standard logging module for each log event.
        It transforms the standard `LogRecord` into a format compatible with Loguru
        and passes it to Loguru's logger.
        """
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        frame, depth = sys._getframe(6), 6
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).bind(
            **self._get_extras()
        ).log(level, record.getMessage())
        if ENABLE_OTEL and ENABLE_OTEL_LOGS:
            from open_webui.utils.telemetry.logs import otel_handler

            otel_handler.emit(record)

    def _get_extras(self):
        if not ENABLE_OTEL:
            return {}

        extras = {}
        context = trace.get_current_span().get_span_context()
        if context.is_valid:
            # Datadog's log-trace correlation requires the reserved keys
            # `dd.trace_id` and `dd.span_id` as decimal strings, with the
            # trace_id truncated to its lower 64 bits. See:
            # https://docs.datadoghq.com/tracing/other_telemetry/connect_logs_and_traces/opentelemetry/
            extras["dd.trace_id"] = str(context.trace_id & 0xFFFFFFFFFFFFFFFF)
            extras["dd.span_id"] = str(context.span_id)
        return extras


def file_format(record: "Record"):
    """
    Formats audit log records into a structured JSON string for file output.

    Parameters:
    record (Record): A Loguru record containing extra audit data.
    Returns:
    str: A JSON-formatted string representing the audit data.
    """

    audit_data = {
        "id": record["extra"].get("id", ""),
        "timestamp": int(record["time"].timestamp()),
        "user": record["extra"].get("user", dict()),
        "audit_level": record["extra"].get("audit_level", ""),
        "verb": record["extra"].get("verb", ""),
        "request_uri": record["extra"].get("request_uri", ""),
        "response_status_code": record["extra"].get("response_status_code", 0),
        "source_ip": record["extra"].get("source_ip", ""),
        "user_agent": record["extra"].get("user_agent", ""),
        "request_object": record["extra"].get("request_object", b""),
        "response_object": record["extra"].get("response_object", b""),
        "extra": record["extra"].get("extra", {}),
    }

    record["extra"]["file_extra"] = json.dumps(audit_data, default=str)
    return "{extra[file_extra]}\n"


def start_logger():
    """
    Initializes and configures Loguru's logger with distinct handlers:

    A console (stdout) handler for general log messages (excluding those marked as auditable).
    An optional file handler for audit logs if audit logging is enabled.
    Additionally, this function reconfigures Python’s standard logging to route through Loguru and adjusts logging levels for Uvicorn.

    Parameters:
    enable_audit_logging (bool): Determines whether audit-specific log entries should be recorded to file.
    """
    logger.remove()

    stdout_filter = lambda record: (
        "auditable" not in record["extra"] if ENABLE_AUDIT_STDOUT else True
    )

    if LOG_FORMAT == "json":
        logger.add(
            stdout_json_sink,
            level=GLOBAL_LOG_LEVEL,
            filter=stdout_filter,
        )
    else:
        logger.add(
            sys.stdout,
            level=GLOBAL_LOG_LEVEL,
            format=stdout_format,
            filter=stdout_filter,
        )
    if AUDIT_LOG_LEVEL != "NONE" and ENABLE_AUDIT_LOGS_FILE:
        try:
            logger.add(
                AUDIT_LOGS_FILE_PATH,
                level="INFO",
                rotation=AUDIT_LOG_FILE_ROTATION_SIZE,
                compression="zip",
                format=file_format,
                filter=lambda record: record["extra"].get("auditable") is True,
            )
        except Exception as e:
            logger.error(f"Failed to initialize audit log file handler: {str(e)}")

    logging.basicConfig(
        handlers=[InterceptHandler()], level=GLOBAL_LOG_LEVEL, force=True
    )

    for uvicorn_logger_name in ["uvicorn", "uvicorn.error"]:
        uvicorn_logger = logging.getLogger(uvicorn_logger_name)
        uvicorn_logger.setLevel(GLOBAL_LOG_LEVEL)
        uvicorn_logger.handlers = []

    for uvicorn_logger_name in AUDIT_UVICORN_LOGGER_NAMES:
        uvicorn_logger = logging.getLogger(uvicorn_logger_name)
        uvicorn_logger.setLevel(GLOBAL_LOG_LEVEL)
        uvicorn_logger.handlers = [InterceptHandler()]

    logger.info(f"GLOBAL_LOG_LEVEL: {GLOBAL_LOG_LEVEL}")
