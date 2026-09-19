import logging
from logging.config import dictConfig


def configure_logging(level: str) -> None:
    dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "format": "%(asctime)s %(levelname)-8s %(name)s: %(message)s",
                },
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "default",
                },
            },
            "root": {"handlers": ["console"], "level": level.upper()},
            "loggers": {
                "uvicorn": {"handlers": ["console"], "level": level.upper(), "propagate": False},
                "uvicorn.access": {
                    "handlers": ["console"],
                    "level": level.upper(),
                    "propagate": False,
                },
            },
        }
    )


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
