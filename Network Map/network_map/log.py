import logging
import logging.handlers
from pathlib import Path

# Default log directory and file
LOG_DIR = Path("/opt/network_map/logs")
LOG_FILE = LOG_DIR / "network_map.log"


def setup_logging(level: int = logging.INFO) -> None:
    """
    Initialize application-wide logging.
    Safe to call multiple times (second call is a no-op).
    """
    if logging.getLogger().handlers:
        # Already configured
        return

    LOG_DIR.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # File handler with rotation
    file_handler = logging.handlers.RotatingFileHandler(
        LOG_FILE,
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(level)

    # Console handler (for systemd/journalctl)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(level)

    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(file_handler)
    root.addHandler(console_handler)


def get_logger(name: str) -> logging.Logger:
    """
    Return a module-specific logger.
    """
    return logging.getLogger(name)
