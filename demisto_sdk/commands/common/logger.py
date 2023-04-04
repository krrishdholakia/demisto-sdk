import logging
import logging.config
import os.path
from logging.handlers import RotatingFileHandler
from pathlib import Path

from demisto_sdk.commands.common.content_constant_paths import CONTENT_PATH

logger: logging.Logger = None  # type: ignore[assignment]

LOG_FILE_NAME: str = "demisto_sdk_debug.log"

LOG_FILE_PATH: Path = CONTENT_PATH / LOG_FILE_NAME
current_log_file_path: Path = LOG_FILE_PATH

DATE_FORMAT = "%Y-%m-%dT%H:%M:%SZ"

DEPRECATED_PARAMETERS = {
    "-v": "--console-log-threshold or --file-log-threshold",
    "-vv": "--console-log-threshold or --file-log-threshold",
    "-vvv": "--console-log-threshold or --file-log-threshold",
    "--verbose": "--console-log-threshold or --file-log-threshold",
    "-q": "--console-log-threshold or --file-log-threshold",
    "--quiet": "--console-log-threshold or --file-log-threshold",
    "-ln": "--log-path",
    "--log-name": "--log-path",
}


def handle_deprecated_args(input_args):
    for current_arg in input_args:
        if current_arg in DEPRECATED_PARAMETERS.keys():
            substitute = DEPRECATED_PARAMETERS[current_arg]
            logging.getLogger("demisto-sdk").error(
                f"[red]Argument {current_arg} is deprecated. Please use {substitute} instead.[/red]"
            )


escapes = {
    "[bold]": "\033[01m",
    "[disable]": "\033[02m",
    "[underline]": "\033[04m",
    "[reverse]": "\033[07m",
    "[strikethrough]": "\033[09m",
    "[invisible]": "\033[08m",
    "[/bold]": "\033[0m",
    "[/disable]": "\033[0m",
    "[/underline]": "\033[0m",
    "[/reverse]": "\033[0m",
    "[/strikethrough]": "\033[0m",
    "[/invisible]": "\033[0m",
    "[black]": "\033[30m",
    "[red]": "\033[91m",
    "[darkred]": "\033[31m",
    "[lightred]": "\033[91m",
    "[darkgrey]": "\033[90m",
    "[lightgrey]": "\033[37m",
    "[green]": "\033[32m",
    "[lightgreen]": "\033[92m",
    "[orange]": "\033[33m",
    "[blue]": "\033[34m",
    "[lightblue]": "\033[94m",
    "[purple]": "\033[35m",
    "[cyan]": "\033[36m",
    "[lightcyan]": "\033[96m",
    "[yellow]": "\033[93m",
    "[pink]": "\033[95m",
    "[/black]": "\033[0m",
    "[/red]": "\033[0m",
    "[/darkred]": "\033[0m",
    "[/lightred]": "\033[0m",
    "[/lightgrey]": "\033[0m",
    "[/darkgrey]": "\033[0m",
    "[/green]": "\033[0m",
    "[/lightgreen]": "\033[0m",
    "[/orange]": "\033[0m",
    "[/blue]": "\033[0m",
    "[/lightblue]": "\033[0m",
    "[/purple]": "\033[0m",
    "[/cyan]": "\033[0m",
    "[/lightcyan]": "\033[0m",
    "[/yellow]": "\033[0m",
    "[/pink]": "\033[0m",
}


def _add_logging_level(
    level_name: str, level_num: int, method_name: str = None
) -> None:
    """
    Comprehensively adds a new logging level to the `logging` module and the
    currently configured logging class.

    `level_name` becomes an attribute of the `logging` module with the value
    `level_num`. `method_name` becomes a convenience method for both `logging`
    itself and the class returned by `logging.getLoggerClass()` (usually just
    `logging.Logger`). If `method_name` is not specified, `level_name.lower()` is
    used.

    To avoid accidental clobberings of existing attributes, this method will
    raise an `AttributeError` if the level name is already an attribute of the
    `logging` module or if the method name is already present

    Example
    -------
    >>> addLoggingLevel('TRACE', logging.DEBUG - 5)
    >>> logging.getLogger(__name__).setLevel("TRACE")
    >>> logging.getLogger(__name__).trace('that worked')
    >>> logging.trace('so did this')
    >>> logging.TRACE
    5

    """
    if not method_name:
        method_name = level_name.lower()

    if hasattr(logging, level_name):
        raise AttributeError(f"{level_name} already defined in logging module")
    if hasattr(logging, method_name):
        raise AttributeError(f"{method_name} already defined in logging module")
    if hasattr(logging.getLoggerClass(), method_name):
        raise AttributeError(f"{method_name} already defined in logger class")

    # This method was inspired by the answers to Stack Overflow post
    # http://stackoverflow.com/q/2183233/2988730, especially
    # http://stackoverflow.com/a/13638084/2988730
    def logForLevel(self, message, *args, **kwargs):
        if self.isEnabledFor(level_num):
            self._log(level_num, message, args, **kwargs)

    def logToRoot(message, *args, **kwargs):
        logging.log(level_num, message, *args, **kwargs)

    logging.addLevelName(level_num, level_name)
    setattr(logging, level_name, level_num)
    setattr(logging.getLoggerClass(), method_name, logForLevel)
    setattr(logging, method_name, logToRoot)


def logging_setup(
    console_log_threshold=logging.INFO,
    file_log_threshold=logging.DEBUG,
    log_file_path=LOG_FILE_PATH,
) -> logging.Logger:
    """Init logger object for logging in demisto-sdk
        For more info - https://docs.python.org/3/library/logging.html

    Args:
        console_log_threshold(int): Minimum console log threshold. Defaults to logging.INFO
        file_log_threshold(int): Minimum console log threshold. Defaults to logging.INFO

    Returns:
        logging.Logger: logger object
    """
    global logger

    SUCCESS_LEVEL: int = 25
    if not hasattr(logging.getLoggerClass(), "success"):
        _add_logging_level("SUCCESS", SUCCESS_LEVEL)

    console_handler = logging.StreamHandler()
    console_handler.set_name("console-handler")
    console_handler.setLevel(
        console_log_threshold if console_log_threshold else logging.INFO
    )

    class ColorConsoleFormatter(logging.Formatter):
        FORMATS = {
            logging.DEBUG: "[lightgrey]%(message)s[/lightgrey]",
            logging.INFO: "[lightgrey]%(message)s[/lightgrey]",
            logging.WARNING: "[yellow]%(message)s[/yellow]",
            logging.ERROR: "[red]%(message)s[/red]",
            logging.CRITICAL: "[red][bold]%(message)s[/bold[/red]",
            SUCCESS_LEVEL: "[green]%(message)s[/green]",
        }

        def __init__(
            self,
        ):
            super().__init__(
                fmt="%(message)s",
                datefmt=DATE_FORMAT,
            )

        @staticmethod
        def _record_contains_escapes(record):
            message = record.getMessage()
            for key in escapes:
                if not key.startswith("[/]") and key in message:
                    return True
            return False

        def format(self, record):
            if ColorConsoleFormatter._record_contains_escapes(record):
                message = logging.Formatter().format(record)
            else:
                log_fmt = self.FORMATS.get(record.levelno)
                message = logging.Formatter(log_fmt).format(record)
            message = self.replace_escapes(message)
            return message

        def replace_escapes(self, message):
            for key in escapes:
                message = message.replace(key, escapes[key])
            return message

    console_formatter = ColorConsoleFormatter()
    console_handler.setFormatter(fmt=console_formatter)

    global current_log_file_path
    current_log_file_path = log_file_path if log_file_path else LOG_FILE_PATH
    if os.path.isdir(current_log_file_path):
        current_log_file_path = current_log_file_path / LOG_FILE_NAME
    file_handler = RotatingFileHandler(
        filename=current_log_file_path,
        mode="a",
        maxBytes=1048576,
        backupCount=10,
    )
    file_handler.set_name("file-handler")
    file_handler.setLevel(file_log_threshold if file_log_threshold else logging.DEBUG)

    class NoColorFileFormatter(logging.Formatter):
        def __init__(
            self,
        ):
            super().__init__(
                fmt="[%(asctime)s] - [%(threadName)s] - [%(levelname)s] - %(filename)s:%(lineno)d - %(message)s",
                datefmt=DATE_FORMAT,
            )

        def format(self, record):
            message = logging.Formatter.format(self, record)
            message = self.replace_escapes(message)
            return message

        def replace_escapes(self, message):
            for key in escapes:
                message = message.replace(key, "")
            return message

    file_formatter = NoColorFileFormatter()
    file_handler.setFormatter(fmt=file_formatter)

    logging.basicConfig(
        handlers=[console_handler, file_handler],
        level=min(console_handler.level, file_handler.level),
    )

    root_logger: logging.Logger = logging.getLogger("")
    set_demisto_handlers_to_logger(root_logger, console_handler, file_handler)

    demisto_logger: logging.Logger = logging.getLogger("demisto-sdk")
    set_demisto_handlers_to_logger(demisto_logger, console_handler, file_handler)
    demisto_logger.propagate = False

    logger = demisto_logger

    return demisto_logger


def set_demisto_handlers_to_logger(
    logger: logging.Logger, console_handler, file_handler
):
    while logger.handlers:
        logger.removeHandler(logger.handlers[0])
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    logger.level = min(console_handler.level, file_handler.level)


def get_log_file() -> Path:
    return current_log_file_path


logging_setup()
