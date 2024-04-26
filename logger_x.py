import argparse
import inspect
import json
import linecache
import logging
import os
import psycopg2
import psycopg2.extras
import socket
import sqlite3
import sys
import textwrap
import traceback
import uvicorn
import uuid

from collections import namedtuple
from datetime import datetime
from dotenv import find_dotenv, load_dotenv, set_key
from fastapi import FastAPI, HTTPException, Header, Depends
from rich.console import Console
from rich.logging import RichHandler
from pydantic import BaseModel
from typing import Any, Dict, NewType, Optional, Sequence, Tuple, Union

# Variables and Type Aliases

PostgresConn = psycopg2.extensions.connection
SQLiteConn = NewType("SQLiteConn", sqlite3.Connection)
DatabaseConn = Union[PostgresConn, SQLiteConn]

Detailed_Result = Tuple[
    bool,
    Optional[Any],
]


DBInfo = namedtuple(
    "DBInfo",
    [
        "logger_mode",
        "logger_dir",
        "database_path",
        "database_user",
        "database_cred",
        "database_host",
        "database_port",
        "database_name",
    ],
)
LogInfo = namedtuple(
    "LogInfo", ["log_notes", "source", "level", "status", "internal"]
)

console = Console()

logging.basicConfig(
    level="NOTSET",
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(rich_tracebacks=True)],
)
logger_x = logging.getLogger("rich")


class NewDBEntry(BaseModel):
    log_notes: Optional[str] = None
    source: Optional[str] = None
    level: Optional[str] = "INFO"
    status: Optional[str] = "new"
    misc: Optional[str] = None
    success: Optional[bool] = False


class UpdateDBLog(BaseModel):
    entry_uuid: str
    status: Optional[str] = None
    status_notes: Optional[str] = None
    internal: Optional[str] = None


def api_listener(
    host: Optional[str] = None,
    port: Optional[int] = None,
    ssl: Optional[Dict[str, str]] = None,
):
    app = FastAPI()

    load_dotenv()

    def verify_secret_key(x_secret_key: str = Header(...)):
        if x_secret_key != os.getenv("SECRET_KEY"):
            raise HTTPException(status_code=403, detail="Invalid secret key")

    @app.post("/add")
    async def add_entry(
        entry: NewDBEntry, secret_key: str = Depends(verify_secret_key)
    ):
        try:
            if entry.success:
                new_log_entry(
                    logging_msg=entry.log_notes if entry.log_notes else None,
                    logging_level=entry.level if entry.level else "INFO",
                    success=True,
                    misc=entry.misc if entry.misc else None,
                )
            new_log_entry(
                logging_msg=entry.log_notes if entry.log_notes else None,
                logging_level=entry.level if entry.level else "ERROR",
                success=False,
                misc=entry.misc if entry.misc else None,
            )
            return {"status": "success"}
        except Exception as e:
            exception = HTTPException(status_code=500, detail=str(e))
            new_log_entry(exception=exception, logging_level="CRITICAL")
            return {"status": "failure"}

    @app.post("/update")
    async def update_entry(
        entry: UpdateDBLog, secret_key: str = Depends(verify_secret_key)
    ):
        try:
            if entry.entry_uuid is None:
                raise HTTPException(
                    status_code=400, detail="entry_uuid cannot be None"
                )
            if (
                entry.status is None
                and entry.status_notes is None
                and entry.internal is None
            ):
                raise HTTPException(
                    status_code=400,
                    detail="Nothing to update.",
                )
            dbmode = os.getenv("LOGGER_MODE", "file")
            dbconnection = None
            if dbmode == "file":
                raise HTTPException(
                    status_code=400,
                    detail="Cannot update a log entry in file mode.",
                )
            elif dbmode == "postgresql":
                dbconnection = connect_database()
            elif dbmode == "sqlite":
                dbconnection = connect_database()
            else:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid database mode: {dbmode}",
                )
            update_db_log(dbconnection, entry.entry_uuid, **entry.dict())
            return {"status": "success"}
        except Exception as e:
            exception = HTTPException(status_code=500, detail=str(e))
            new_log_entry(exception=exception, logging_level="CRITICAL")
            return {"status": "failure"}

    api_host = os.getenv("API_HOST", "0.0.0.0") if host is None else host
    api_port = os.getenv("API_PORT", 8000) if port is None else port
    ssl_key_file = (
        os.getenv("SSL_KEY_FILE", None) if ssl is None else ssl["key"]
    )
    ssl_cert_file = (
        os.getenv("SSL_CERT_FILE", None) if ssl is None else ssl["cert"]
    )
    ssl_enabled = (
        True
        if (ssl_key_file is not None and ssl_cert_file is not None)
        else False
    )

    uvicorn_args = {
        "host": api_host,
        "port": api_port,
    }

    if ssl_enabled:
        uvicorn_args["ssl_keyfile"] = ssl_key_file
        uvicorn_args["ssl_certfile"] = ssl_cert_file

    uvicorn.run(app, **uvicorn_args)


def build_debug_message(
    date_time: Optional[str] = None,
    level: Optional[str] = None,
    log_notes: Optional[str] = None,
    source: Optional[str] = None,
    status: Optional[str] = None,
    internal: Optional[str] = None,
) -> str:
    rich_datetime = datetime.utcnow() if date_time is None else date_time
    rich_level = "ERROR" if level is None else level
    rich_log_notes = (
        "Something went wrong (generic error message)."
        if log_notes is None
        else log_notes
    )
    rich_source = socket.getfqdn().lower() if source is None else source
    rich_status = "new" if status is None else status

    try:
        debug_message = (
            f"date_time:     {rich_datetime}\n"
            f"level:         {rich_level}\n"
            f"log_notes:     {rich_log_notes}\n"
            f"source:        {rich_source}\n"
            f"status:        {rich_status}\n"
        )
        if internal:
            debug_message += f"internal:      {internal}\n"
        debug_message += "\n"
        return debug_message
    except Exception as e:
        error_message = (
            f"Error in build_debug_message(): {e}\n\n"
            "Something went really really wrong here..."
        )
        return error_message


def check_function(
    path: str, create_dir: bool = False, is_directory: bool = True
) -> bool:
    if os.path.exists(path):
        if (is_directory and os.path.isdir(path)) or (
            not is_directory and os.path.isfile(path)
        ):
            return True
        else:
            expected_type = "directory" if is_directory else "file"
            raise ValueError(f"{path} is not a {expected_type}")
    if is_directory:
        if create_dir:
            os.makedirs(path, exist_ok=True)
            return True
        else:
            raise FileNotFoundError(f"Directory {path} does not exist")
    else:
        raise FileNotFoundError(f"File {path} does not exist")


def close_database(connection) -> Optional[bool]:
    try:
        connection.close()
        return True
    except Exception as e:
        raise Exception(f"[close_database({type(connection)}) failed]:{e}")


def connect_database(
    data_path: Optional[str] = None,
) -> Union[PostgresConn, SQLiteConn]:
    load_dotenv()

    def postgresql_connect() -> PostgresConn:
        try:
            connection = psycopg2.connect(
                dbname=os.getenv("DATABASE_NAME", "logger"),
                user=os.getenv("DATABASE_USER", "root"),
                password=os.getenv("DATABASE_CRED", "password"),
                host=os.getenv("DATABASE_HOST", "localhost"),
                port=os.getenv("DATABASE_PORT", 5432),
            )
            return connection
        except Exception as e:
            raise Exception(
                f"[Failed postgresql_connect() in logger.db_connect()]:{e}"
            )

    def sqlite_connect(db_path: Optional[str] = None) -> SQLiteConn:
        try:
            if db_path != ":memory:":
                if db_path is None:
                    db_path = os.getenv("DATABASE_PATH", ":memory:")
                connection = sqlite3.connect(str(db_path))
            else:
                connection = sqlite3.connect(":memory:")
            return SQLiteConn(connection)
        except Exception as e:
            raise Exception(
                f"[Failed sqlite_connect({db_path}) in logger.db_connect()]:{e}"
            )

    try:
        logger_mode = os.getenv("LOGGER_MODE", "file")
        if logger_mode == "postgresql":
            return postgresql_connect()
        elif logger_mode == "sqlite":
            return sqlite_connect(data_path)
        elif logger_mode == "file":
            raise Exception(
                "This should not be happening."
                "db_connect() called with logger_mode set to file."
            )
        else:
            raise Exception(f"{logger_mode} is either invalid or unsupported.")
    except Exception as e:
        err_1 = "[connect_database("
        err_2 = f"{os.getenv('DATABASE_MODE', '')}) failed]:{e}"
        raise Exception(err_1 + err_2)


def convert_sequence_to_dict(
    values: Sequence[Union[int, str, bytes, float, None]]
) -> Dict[str, Union[int, str, bytes, float, None]]:
    return {str(i): value for i, value in enumerate(values)}


def create_db_log(log_info: LogInfo, db_connection: DatabaseConn) -> bool:
    """
    Insert a new log entry into the database logger.
    """
    cursor = None
    try:
        cursor = db_connection.cursor()
        if isinstance(db_connection, PostgresConn):
            cursor.execute(
                """
                INSERT INTO logger
                (level, source, log_notes, status, internal)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    log_info.level,
                    log_info.source,
                    log_info.log_notes,
                    log_info.status,
                    log_info.internal,
                ),
            )
        elif type(db_connection) == SQLiteConn:
            cursor.execute(
                """
                INSERT INTO logger
                (level, source, log_notes, status, uuid, internal)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    log_info.level,
                    log_info.source,
                    log_info.log_notes,
                    log_info.status,
                    str(uuid.uuid4()),
                    log_info.internal,
                ),
            )

        else:
            raise Exception(
                f"Invalid database mode: {os.environ['LOGGER_MODE']}"
            )
        db_connection.commit()
        cursor.close() if cursor else None
        return True
    except Exception as e:
        cursor.close() if cursor else None
        close_database(db_connection) if db_connection else None
        error_message = build_debug_message(
            level=log_info.level,
            log_notes=log_info.log_notes,
            source=log_info.source,
            status=log_info.status,
            internal=log_info.internal,
        )
        logger_x.critical(
            f"[create_database_log({type(db_connection)}) failed]\n"
            f"[Exception]:{e}\n\n"
            f"[Detailed Info]:\n{error_message}"
        )
        return False


def create_new_database(db_connection: DatabaseConn) -> bool:
    """
    Create a new logger database.
    """
    cursor = None
    try:
        cursor = db_connection.cursor()
        if isinstance(db_connection, PostgresConn):
            cursor.execute(
                """
                CREATE TABLE logger (
                    id SERIAL PRIMARY KEY,
                    datetime TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    level VARCHAR(32) NOT NULL,
                    source VARCHAR(1024) NOT NULL,
                    log_notes TEXT,
                    status VARCHAR(255) NOT NULL DEFAULT 'new',
                    status_notes TEXT,
                    last_updated TIMESTAMP,
                    uuid VARCHAR(255) NOT NULL UNIQUE DEFAULT uuid_generate_v4(),
                    internal JSONB
                )
                """
            )
        elif type(db_connection) == SQLiteConn:
            cursor.execute(
                """
                CREATE TABLE logger (
                    id INTEGER PRIMARY KEY,
                    datetime TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    level VARCHAR(32) NOT NULL,
                    source VARCHAR(1024) NOT NULL,
                    log_notes TEXT,
                    status VARCHAR(255) NOT NULL DEFAULT 'new',
                    status_notes TEXT,
                    last_updated TIMESTAMP,
                    uuid UUID NOT NULL UNIQUE,
                    internal TEXT
                )
                """
            )
        else:
            raise Exception(
                f"[create_new_database({type(db_connection)}) failed]:"
                f"Invalid database mode: {os.environ['LOGGER_MODE']}"
            )
        db_connection.commit()
        cursor.close() if cursor else None
        return True
    except Exception as e:
        cursor.close() if cursor else None
        close_database(db_connection) if db_connection else None
        logging_info = build_debug_message(
            level="CRITICAL",
            log_notes=str(e),
        )
        new_log_entry(e, logging_info, "CRITICAL")
        return False


def dir_check(dir_path: str, create_dir: bool = True) -> bool:
    return check_function(dir_path, create_dir, is_directory=True)


def fetch_log_path() -> str:
    try:
        log_dir = os.path.join(
            os.getenv("LOGGER_DIR", os.path.join(os.getcwd(), ".logs"))
        )
        today = datetime.utcnow()
        time_stamp = today.strftime("%Y%m%d")
        if not dir_check(log_dir):
            raise FileNotFoundError(
                f"[{log_dir}] does not exist. Please create it and try again."
            )
        return os.path.join(log_dir, f"{time_stamp}.log")
    except Exception as e:
        raise RuntimeError(f"[fetch_log_path() failed]: {e}")


def file_exists(file_path: str) -> bool:
    return check_function(file_path, is_directory=False)


def format_datetime(
    input_time: datetime, milliseconds: bool = False
) -> Optional[str]:
    try:
        if isinstance(input_time, (int, float)):
            input_time = datetime.fromtimestamp(input_time / 1000)
        else:
            input_time = datetime.strptime(
                str(input_time), "%Y-%m-%d %H:%M:%S.%f"
            )
        if milliseconds:
            return input_time.strftime("%Y-%m-%d %H:%M:%S.%f")
        else:
            return input_time.strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError) as e:
        err_1 = f"[format_datetime({input_time})"
        err_2 = f", {milliseconds}" if milliseconds else ""
        err_3 = f"] failed: {e}"
        raise Exception(err_1 + err_2 + err_3)


def get_database_info(database_info: Optional[DBInfo]) -> Optional[DBInfo]:
    env_info = get_env()
    merged_info = {
        key: (
            getattr(database_info, key)
            if database_info and getattr(database_info, key) is not None
            else value
        )
        for key, value in env_info._asdict().items()
    }
    return DBInfo(**merged_info)


def get_env() -> DBInfo:
    load_dotenv()
    logger_mode = os.getenv("LOGGER_MODE", "file")
    logger_dir = os.getenv("LOGGER_DIR", ".logs")
    database_path = os.getenv("DATABASE_PATH", ":memory:")
    database_user = os.getenv("DATABASE_USER", "root")
    database_cred = os.getenv("DATABASE_CRED", "password")
    database_host = os.getenv("DATABASE_HOST", "localhost")
    database_port = os.getenv("DATABASE_PORT", 5432)
    database_name = os.getenv("DATABASE_NAME", "logger")

    env_info = DBInfo(
        logger_mode,
        logger_dir,
        database_path,
        database_user,
        database_cred,
        database_host,
        database_port,
        database_name,
    )

    return env_info


def json_to_string(json_package: Dict[str, str]) -> Detailed_Result:
    try:
        json_converted = json.dumps(
            json_package, ensure_ascii=False, separators=(",", ":")
        )
        if json_converted is None:
            return False, f"{json_converted} is None"
        if not isinstance(json_converted, str):
            try:
                json_converted = str(json_converted)
            except ValueError:
                return False, f"{json_converted} is a {type(json_converted)}"
        if len(json_converted) == 0:
            return False, f"{json_converted} is empty"
        return True, json_converted
    except (TypeError, ValueError) as e:
        return False, f"[json_to_string() failed]: {e}"


def json_validator(
    json_package: Union[Dict[str, str], str], convert_to_string: bool = True
) -> Detailed_Result:
    try:
        if isinstance(json_package, dict):
            for key, value in json_package.items():
                key_check = string_validator(key)
                value_check = string_validator(value)
                if not key_check[0]:
                    return key_check
                if not value_check[0]:
                    return value_check
            if convert_to_string:
                return json_to_string(json_package)
            else:
                return True, json_package
        elif isinstance(json_package, str):
            try:
                json.loads(json_package)
                return True, json_package
            except json.JSONDecodeError:
                return False, "Invalid JSON string"
        else:
            return False, "Invalid input type"
    except Exception as e:
        return False, (f"[json_validator() failed]: {e}")


def log_to_file(
    log_message: str,
    level: str = "INFO",
) -> bool:
    wrap_text_at = 80
    today = str(format_datetime(datetime.utcnow())).split(" ")[0]
    now = datetime.utcnow()
    try:
        log_file = fetch_log_path()
        is_new_file = not os.path.exists(log_file)
        if not is_new_file:
            formatted_message = f"[{now}] [{level}] {log_message}"
        else:
            formatted_message = f"[{now}] ***START_OF_LOG for {today}***"
        wrapped_message = textwrap.fill(formatted_message, width=wrap_text_at)
        with open(log_file, "a") as f:
            f.write(wrapped_message + "\n")
        return True
    except Exception as e:
        raise Exception(f"[log_to_file() failed]: {e}")


def main_console():
    # TODO: build console interface for .env configuration, log viewing/updating,
    # log searching, log exporting, and api listener launcher/management
    raise NotImplementedError("Console is not implemented yet.")


def main_gui():
    # TODO: build GUI in PyQt6 for .env configuration, log viewing/updating,
    # log searching, log exporting, and api listener launcher/management
    raise NotImplementedError("GUI is not implemented yet.")


def new_log_entry(
    exception: Optional[Exception] = None,
    logging_msg: Optional[str] = None,
    logging_level: str = "ERROR",
    success: bool = False,
    console: bool = False,
    misc: Optional[str] = None,
) -> Union[bool, Detailed_Result]:
    db_connection = None
    dbinfo = set_env()
    if dbinfo["logger_mode"] == "file":
        result = log_to_file(
            (
                (f"{logging_msg}. Exception: {exception}")
                if logging_msg
                else str(exception)
            ),
            logging_level,
        )
        return result
    else:
        try:
            complete_package = {}
            if not success:

                def format_traceback(tb):
                    formatted_trace = []
                    for frame_summary in tb:
                        args, _, _, values = inspect.getargvalues(
                            frame_summary[0]
                        )
                        args_str = ", ".join(
                            f"{arg}={values[arg]}" for arg in args
                        )
                        line_str = linecache.getline(
                            frame_summary.filename, frame_summary.lineno
                        ).strip()
                        line_str = line_str if line_str else "N/A"

                        formatted_trace.append(
                            f'"{frame_summary.name}({args_str})": '
                            f'line {frame_summary.lineno}, "{line_str}"'
                        )
                    return " -> called from -> ".join(formatted_trace[::-1])

                if exception is None:
                    misc = "No exception provided." + (
                        " " + misc if misc else ""
                    )
                    complete_package = {
                        "level": logging_level,
                        "source": f"[{socket.getfqdn().lower()}]",
                        "log_notes": logging_msg,
                        "status": "new",
                        "internal": {
                            key: value
                            for key, value in {
                                "full_trace": None,
                                "location": None,
                                "short_trace": None,
                                "misc": misc,
                            }.items()
                            if value is not None
                        },
                    }
                else:
                    tb = traceback.extract_tb(exception.__traceback__)
                    collected_error_info = format_traceback(tb)
                    filename, line_no, function_name, _ = tb[-1]
                    error_host_file = (
                        f"[{socket.getfqdn().lower()}]"
                        f"[{os.path.basename(filename)}]"
                    )
                    error_source = f"[{filename}:{line_no}][{function_name}()]"
                    error_message = f"{error_source}[{exception}]"

                    complete_package = {
                        "level": logging_level,
                        "source": error_host_file,
                        "log_notes": error_message,
                        "status": "new",
                        "internal": {
                            key: value
                            for key, value in {
                                "full_trace": collected_error_info,
                                "location": error_source,
                                "short_trace": str(exception),
                                "misc": misc,
                            }.items()
                            if value is not None
                        },
                    }
            else:
                complete_package = {
                    "level": "SUCCESS",
                    "source": f"[{socket.getfqdn().lower()}]",
                    "log_notes": logging_msg,
                    "status": "new",
                    "internal": {
                        key: value
                        for key, value in {
                            "misc": misc,
                        }.items()
                        if value is not None
                    },
                }
            internal_prep = json_validator(complete_package["internal"])
            internal = internal_prep[1] if internal_prep[0] else None

            if console or os.environ.get("FORCE_DEBUG") == "True":
                debug_message = build_debug_message(
                    level=complete_package["level"],
                    log_notes=complete_package["log_notes"],
                    source=complete_package["source"],
                    status=complete_package["status"],
                    internal=internal,
                )
                if logging_level == "ERROR":
                    logger_x.error(debug_message)
                elif logging_level == "CRITICAL":
                    logger_x.critical(debug_message)
                elif logging_level == "WARNING":
                    logger_x.warning(debug_message)
                elif logging_level == "DEBUG":
                    logger_x.debug(debug_message)
                else:
                    logger_x.info(debug_message)

            logging_info = LogInfo(
                log_notes=complete_package["log_notes"],
                source=complete_package["source"],
                level=complete_package["level"],
                status=complete_package["status"],
                internal=internal,
            )

            try:
                dbpath = dbinfo["database_path"] if dbinfo else None
                db_connection = connect_database(dbpath)
                if db_connection is not None and not hasattr(
                    db_connection, "rollback"
                ):
                    raise TypeError(
                        f"Expected a database connection, "
                        f"but got {type(db_connection).__name__}"
                    )
                result = create_db_log(logging_info, db_connection)
                close_database(db_connection) if db_connection else None
                if not result:
                    raise Exception(
                        "create_db_log() failed. Trying log_to_file()."
                    )
                else:
                    return True
            except Exception as db_log_exception:
                close_database(db_connection) if db_connection else None
                internal_info = {
                    key: value
                    for key, value in {
                        "original_exception": str(exception),
                        "original_message": logging_msg,
                        "original_level": logging_level,
                        "original_success_flag": success,
                        "original_console_flag": console,
                        "original_misc": misc,
                    }.items()
                    if value is not None
                }
                internal_info_prep = json_validator(internal_info)
                internal_info = (
                    internal_info_prep[1] if internal_info_prep[0] else None
                )
                if console or os.environ.get("FORCE_DEBUG") == "True":
                    logging_msg = build_debug_message(
                        level="CRITICAL",
                        log_notes=str(db_log_exception),
                        internal=internal_info,
                    )
                    logger_x.critical(logging_msg)
                log_to_file(
                    f"[create_db_log() failed]: {db_log_exception}",
                    "CRITICAL",
                )
                log_to_file(
                    (
                        str(internal_info)
                        if internal_info
                        else "[Failed to retrieve original logging info.]"
                    ),
                    "CRITICAL",
                )
                return False, "Catastrophic Logging Failure"

        except Exception as e:
            close_database(db_connection) if db_connection else None
            log_to_file(f"[Failed to log to database.]: {e}", "CRITICAL")
            internal_info = {
                key: value
                for key, value in {
                    "original_exception": str(exception),
                    "original_message": logging_msg,
                    "original_level": logging_level,
                    "original_success_flag": success,
                    "original_console_flag": console,
                    "original_misc": misc,
                }.items()
                if value is not None
            }
            internal_info_prep = json_validator(internal_info)
            internal_info = (
                internal_info_prep[1] if internal_info_prep[0] else None
            )
            if console or os.environ.get("FORCE_DEBUG") == "True":
                logging_msg = build_debug_message(
                    level="CRITICAL",
                    log_notes=str(e),
                    internal=internal_info,
                )
                if logging_level == "ERROR":
                    logger_x.error(debug_message)
                elif logging_level == "CRITICAL":
                    logger_x.critical(debug_message)
                elif logging_level == "WARNING":
                    logger_x.warning(debug_message)
                elif logging_level == "DEBUG":
                    logger_x.debug(debug_message)
                else:
                    logger_x.info(debug_message)
            log_to_file(
                (
                    str(internal_info)
                    if internal_info
                    else "[Failed to retrieve original logging info.]"
                ),
                "CRITICAL",
            )

            return False, "Huge Logging Failure"


def revert_characters(formatted_str: str) -> str:
    subs: Dict[str, str] = {
        "⟦": "[",
        "⟧": "]",
        "⦃": "{",
        "⦄": "}",
        "❨": "(",
        "❩": ")",
        "‚": ",",
        "⁏": ";",
        "❮": "<",
        "❯": ">",
    }
    original_str = formatted_str
    for char, sub in subs.items():
        original_str = original_str.replace(char, sub)
    return original_str


def set_env(
    new_info: Optional[DBInfo] = None, overwrite: bool = True
) -> Dict[str, str]:
    supported_servers = ["postgresql"]
    supported_file_db = ["sqlite"]
    other_supported = ["file"]
    set_items = {}
    try:
        dotenv_path = find_dotenv()
        if not dotenv_path:
            dotenv_path = ".env"
            with open(dotenv_path, "w"):
                pass
        load_dotenv(dotenv_path)
        if new_info is None:
            new_info = get_env()
        if new_info.logger_mode in other_supported:
            keys_to_set = ["logger_mode", "logger_dir"]
        elif new_info.logger_mode in supported_servers:
            keys_to_set = [
                "logger_mode",
                "logger_dir",
                "database_user",
                "database_cred",
                "database_host",
                "database_port",
                "database_name",
            ]
        elif new_info.logger_mode in supported_file_db:
            keys_to_set = ["logger_mode", "logger_dir", "database_path"]
        else:
            logger_x.warning(
                "Invalid logger_mode, defaulting to file as logger_mode"
            )
            new_info = new_info._replace(logger_mode="file")
            keys_to_set = ["logger_mode", "logger_dir"]
        for key in keys_to_set:
            value = getattr(new_info, key)
            if overwrite or os.getenv(key) is None:
                set_key(dotenv_path, key, str(value))
                os.environ[key] = str(value)
                set_items[key] = str(value)
        return set_items
    except Exception as e:
        logger_x.error(
            "Could not write to .env in set_env(). "
            "Attempting to write to memory instead."
            f"Error_Info: {e}"
        )
        try:
            if new_info is None:
                new_info = get_env()
            for key, value in new_info._asdict().items():
                os.environ[key] = str(value)
                set_items[key] = str(value)
            return set_items
        except Exception as e2:
            logger_x.error(
                "Could not write to memory either. "
                f"Error in set_env(): {e2}"
            )
            exit(1)


def string_validator(string: str, clean: bool = True) -> Detailed_Result:
    try:
        if string is None:
            return False, f"{string} is None"
        if not isinstance(string, str):
            try:
                string = str(string)
            except ValueError:
                return False, f"{string} is a {type(string)}"
        if len(string) == 0:
            return False, f"{string} is empty"
        if clean:
            cleaned_string = substitute_characters(string)
            return True, cleaned_string
        else:
            return True, string
    except ValueError as e:
        return False, f"An error occurred during string validation: {e}"


def substitute_characters(original_str: str) -> str:
    subs: Dict[str, str] = {
        "[": "⟦",
        "]": "⟧",
        "{": "⦃",
        "}": "⦄",
        "(": "❨",
        ")": "❩",
        ",": "‚",
        ";": "⁏",
        "<": "❮",
        ">": "❯",
    }
    formatted_str = original_str
    for char, sub in subs.items():
        formatted_str = formatted_str.replace(char, sub)
    return formatted_str


def update_db_log(db_connection: DatabaseConn, entry_uuid, **kwargs) -> bool:
    """
    Update an existing log entry in the database logger.
    """
    if not entry_uuid:
        raise ValueError("entry_uuid is required to update a log entry.")
    status = kwargs.get("status")
    status_notes = kwargs.get("status_notes")
    internal = kwargs.get("internal")
    if None in [status, status_notes, internal]:
        raise ValueError(
            "Missing one or more required arguments: "
            "status, status_notes, internal\n"
            "There is nothing to update."
        )
    set_clause = []
    where_clause = []
    values = []
    cursor = None
    try:
        cursor = db_connection.cursor()
        if isinstance(db_connection, PostgresConn):
            if status is not None:
                set_clause.append("status = %s")
                values.append(status)
            if status_notes is not None:
                set_clause.append("status_notes = %s")
                values.append(status_notes)
            if internal is not None:
                set_clause.append("internal = %s")
                values.append(json.dumps(internal))
            where_clause.append("uuid = %s")
        elif type(db_connection) == SQLiteConn:
            if status is not None:
                set_clause.append("status = ?")
                values.append(status)
            if status_notes is not None:
                set_clause.append("status_notes = ?")
                values.append(status_notes)
            if internal is not None:
                set_clause.append("internal = ?")
                values.append(json.dumps(internal))
            where_clause.append("uuid = ?")
        else:
            raise Exception(
                f"Invalid database mode: {os.environ['LOGGER_MODE']}"
            )
        set_clause.append("last_updated = CURRENT_TIMESTAMP")
        set_clause_str = ", ".join(set_clause)
        where_clause_str = " AND ".join(where_clause)
        values.append(entry_uuid)
        query = f"UPDATE logger SET {set_clause_str} WHERE {where_clause_str}"
        cursor.execute(query, tuple(values))
        db_connection.commit()
        cursor.close() if cursor else None
        close_database(db_connection) if db_connection else None
        return True
    except Exception as e:
        exception_error_level = "CRITICAL"
        cursor.close() if cursor else None
        close_database(db_connection) if db_connection else None
        logging_data = {
            key: value
            for key, value in {
                "status": status,
                "status_notes": status_notes,
                "internal": internal,
                "uuid": uuid,
            }.items()
        }
        logging_data_prep = json_validator(logging_data)
        logging_data = logging_data_prep[1] if logging_data_prep[0] else None
        logging_info = build_debug_message(
            level=exception_error_level,
            log_notes=str(e),
            internal=logging_data,
        )
        new_log_entry(e, logging_info, exception_error_level)
        return False


if __name__ == "__main__":
    try:
        load_dotenv()
        parser = argparse.ArgumentParser(description="Logger by GDV, LLC v1.0")

        parser.add_argument(
            "-a",
            "--add",
            help="Log a new entry (json with msg, lvl, success, misc).",
            type=json.loads,
        )
        parser.add_argument(
            "-u",
            "--update",
            help="Update a log entry (json with uuid, status, notes, internal).",
            type=json.loads,
        )

        parser.add_argument(
            "-g",
            "--gui",
            help="Launch GUI (no parameters)",
            action="store_true",
        )
        parser.add_argument(
            "-l",
            "--listener",
            help="Start API Listener (for custom use args -i -p -s)",
            action="store_true",
        )
        parser.add_argument(
            "-c",
            "--console",
            help="Launch Console (no parameters)",
            action="store_true",
        )

        parser.add_argument(
            "-i", "--ip", help="IP/Host for API listener (string)"
        )
        parser.add_argument(
            "-p", "--port", help="Port for API listener (integer)", type=int
        )
        parser.add_argument(
            "-s",
            "--ssl",
            help="SSL config for API listener (json with key, cert)",
            type=json.loads,
        )

        args = parser.parse_args()

        if args.add:
            new_log_entry(**args.add)
        elif args.update:
            update_db_log(**args.update)
        elif args.gui:
            main_gui()
        elif args.listener:
            ip = args.ip or "0.0.0.0"
            port = args.port or 8000
            ssl = args.ssl if args.ssl else None
            api_listener(ip, port, ssl)
        elif args.console:
            main_console()
        else:
            message = (
                "No valid arguments provided. Please configure 'auto' in .env "
                "or use arguments to run.\n"
                "Options: -a/--add, -u/--update, -g/--gui, -l/--listener, -c/--console"
            )
            logger_x.critical(message)
            sys.exit(1)
        sys.exit(0)
    except Exception as e:
        error_msg = f"[main() failed]: {e}"
        logger_x.critical(error_msg)
        sys.exit(1)
