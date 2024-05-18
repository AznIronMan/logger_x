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
from dotenv import dotenv_values, find_dotenv, load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from rich.console import Console
from rich.logging import RichHandler
from pydantic import BaseModel, Field
from typing import Any, Dict, NewType, Optional, Tuple, Union


# TODO: Add docstrings to all functions and classes
# TODO: Consider tighening the CORS settings

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
        "LOGGER_MODE",
        "LOGGER_DIR",
        "DATABASE_PATH",
        "DATABASE_USER",
        "DATABASE_CRED",
        "DATABASE_HOST",
        "DATABASE_PORT",
        "DATABASE_NAME",
    ],
)
FullLogInfo = namedtuple(
    "FullLogInfo",
    ["log_id", "uuid", "log_notes", "source", "level", "internal"],
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


class FullDBEntry(BaseModel):
    """
    Pydantic model that includes the standard
    fillable fields for a database entry.
    """

    log_notes: Optional[str] = None
    source: Optional[str] = None
    level: Optional[str] = "INFO"
    status: Optional[str] = "new"
    misc: Optional[str] = None
    success: Optional[bool] = False


class UpdateDBLog(BaseModel):
    """
    Pydantic model that includes the standard
    updatable fields for a database entry.
    """

    entry_uuid: str
    status: Optional[str] = None
    status_notes: Optional[str] = None
    internal: Optional[str] = None


def api_listener(
    host: Optional[str] = None,
    port: Optional[int] = None,
    ssl: Optional[Dict[str, str]] = None,
):
    """
    FastAPI listener that listens for incoming
    API requests and processes them accordingly.
    """
    app = FastAPI()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    load_dotenv(find_dotenv(usecwd=True))

    def verify_secret_key(x_secret_key: str = Header(...)):
        if x_secret_key != os.getenv("SECRET_KEY"):
            raise HTTPException(status_code=403, detail="Invalid secret key")

    @app.post("/add")
    async def api_add_entry(
        entry: FullDBEntry, secret_key: str = Depends(verify_secret_key)
    ):
        """
        API endpoint that adds a new entry to the database.
        """
        try:
            determined_level = (
                entry.level
                if entry.level is not None
                else ("ERROR" if not entry.success else "INFO")
            )
            new_log_entry(
                logging_msg=entry.log_notes,
                logging_level=determined_level,
                source=entry.source,
                success=(
                    bool(entry.success) if entry.success is not None else False
                ),
                misc=entry.misc,
            )
            return {"status": "success"}
        except Exception as e:
            exception = HTTPException(status_code=500, detail=str(e))
            new_log_entry(exception=exception, logging_level="CRITICAL")
            return {"status": "failure"}

    @app.post("/update/{entry_uuid}")
    async def api_update_entry_by_uuid(
        entry_uuid: str,
        entry: FullDBEntry,
        secret_key: str = Depends(verify_secret_key),
    ):
        """
        API endpoint that updates an existing entry in the database.
        """
        try:
            determined_level = (
                entry.level
                if entry.level is not None
                else ("ERROR" if not entry.success else "INFO")
            )
            result = update_db_log_by_uuid(
                uuid=entry_uuid,
                logging_msg=entry.log_notes,
                logging_level=determined_level,
                source=entry.source,
                status=(entry.status if entry.status is not None else "new"),
                misc=entry.misc if entry.misc is not None else None,
            )
            return {"status": "success" if result else "failure"}
        except Exception as e:
            exception = HTTPException(status_code=500, detail=str(e))
            new_log_entry(exception=exception, logging_level="CRITICAL")
            return {"status": "failure"}

    @app.get("/firstlogid")
    async def api_first_log_id(secret_key: str = Depends(verify_secret_key)):
        """
        API endpoint that fetches the first log ID in the database.
        """
        try:
            db_connection = connect_database()
            first_id = get_first_log_id(db_connection)
            close_database(db_connection)
            return {"first_log_id": first_id}
        except Exception as e:
            logger_x.error(
                f"Failed to fetch first log ID: {str(e)}", exc_info=True
            )
            raise HTTPException(
                status_code=500, detail="Failed to fetch first log ID"
            )

    @app.get("/newlogid")
    async def api_new_log_id(secret_key: str = Depends(verify_secret_key)):
        """
        API endpoint that fetches the next available log ID.
        """
        try:
            db_connection = connect_database()
            new_id = get_new_log_id(db_connection)
            close_database(db_connection)
            return {"new_log_id": new_id}
        except Exception as e:
            logger_x.error(
                f"Failed to fetch new log ID: {str(e)}", exc_info=True
            )
            raise HTTPException(
                status_code=500, detail="Failed to fetch new log ID"
            )

    @app.get("/nextlogid/{current_id}")
    async def api_next_log_id(
        current_id: int, secret_key: str = Depends(verify_secret_key)
    ):
        """
        API endpoint that fetches the next log ID after the current one.
        """
        try:
            db_connection = connect_database()
            try:
                next_id = get_next_log_id(current_id, db_connection)
                return {"next_log_id": next_id}
            except ValueError as ve:
                return {"next_log_id": None, "message": str(ve)}
            finally:
                close_database(db_connection)
        except Exception as e:
            logger_x.error(
                f"Failed to fetch next log ID: {str(e)}", exc_info=True
            )
            raise HTTPException(
                status_code=500, detail="Failed to fetch next log ID"
            )

    @app.get("/previouslogid/{current_id}")
    async def api_previous_log_id(
        current_id: int, secret_key: str = Depends(verify_secret_key)
    ):
        """
        API endpoint that fetches the previous log ID before the current one.
        """
        try:
            db_connection = connect_database()
            try:
                previous_id = get_previous_log_id(current_id, db_connection)
                return {"previous_log_id": previous_id}
            except ValueError as ve:
                return {"previous_log_id": None, "message": str(ve)}
            finally:
                close_database(db_connection)
        except Exception as e:
            logger_x.error(
                f"Failed to fetch previous log ID: {str(e)}", exc_info=True
            )
            raise HTTPException(
                status_code=500, detail="Failed to fetch previous log ID"
            )

    @app.get("/uuid/{log_id}")
    async def api_get_uuid(
        log_id: int, secret_key: str = Depends(verify_secret_key)
    ):
        """
        API endpoint that fetches the UUID for a given log ID.
        """
        try:
            db_connection = connect_database()
            uuid = get_uuid_by_log_id(db_connection, log_id)
            close_database(db_connection)
            if uuid:
                return {"uuid": uuid}
            else:
                raise HTTPException(status_code=404, detail="Log ID not found")
        except Exception as e:
            exception = HTTPException(status_code=500, detail=str(e))
            new_log_entry(exception=exception, logging_level="CRITICAL")
            return {"status": "failure"}

    @app.get("/getlog/{uuid}")
    async def api_get_log(
        uuid: str, secret_key: str = Depends(verify_secret_key)
    ):
        """
        API endpoint that fetches a log entry by UUID.
        """
        try:
            db_connection = connect_database()
            log = get_log_by_uuid(db_connection, uuid)
            close_database(db_connection)
            if log:
                return log
            else:
                raise HTTPException(status_code=404, detail="UUID not found")
        except Exception as e:
            exception = HTTPException(status_code=500, detail=str(e))
            new_log_entry(exception=exception, logging_level="CRITICAL")
            return {"status": "failure"}

    @app.get("/checkid/{log_id}")
    async def api_check_log_id(
        log_id: int, secret_key: str = Depends(verify_secret_key)
    ):
        """
        API endpoint that checks if a log ID exists in the database.
        """
        try:
            db_connection = connect_database()
            check = check_log_id_exists(db_connection, log_id)
            close_database(db_connection)
            return {"exists": check}
        except Exception as e:
            exception = HTTPException(status_code=500, detail=str(e))
            new_log_entry(exception=exception, logging_level="CRITICAL")
            return {"status": "failure"}

    @app.delete("/admindeletelog/{log_id}/{uuid}/")
    async def api_delete_log(
        log_id: int,
        uuid: str,
        secret_key: str = Depends(verify_secret_key),
    ):
        """
        API endpoint that allows an admin to delete a log entry.
        """
        try:
            db_connection = connect_database()
            cursor = db_connection.cursor()

            if not check_log_id_exists(db_connection, log_id):
                cursor.close()
                close_database(db_connection)
                raise HTTPException(
                    status_code=404, detail="Log ID and UUID not found"
                )

            result = delete_log_admin(db_connection, log_id, uuid)

            cursor.close()
            close_database(db_connection)
            return result
        except Exception as e:
            exception = HTTPException(status_code=500, detail=str(e))
            new_log_entry(exception=exception, logging_level="CRITICAL")
            close_database(db_connection)
            return {"status": "failure"}

    @app.delete("/deletelog/{log_id}/{uuid}/")
    async def api_update_log_to_deleted(
        log_id: int,
        uuid: str,
        secret_key: str = Depends(verify_secret_key),
    ):
        """
        API endpoint that updates a log entry to a deleted status.
        """
        try:
            db_connection = connect_database()
            cursor = db_connection.cursor()

            if not check_log_id_exists(db_connection, log_id):
                cursor.close()
                close_database(db_connection)
                raise HTTPException(
                    status_code=404, detail="Log ID and UUID not found"
                )

            result = set_log_to_deleted(db_connection, log_id, uuid)

            cursor.close()
            close_database(db_connection)
            return result
        except Exception as e:
            exception = HTTPException(status_code=500, detail=str(e))
            new_log_entry(exception=exception, logging_level="CRITICAL")
            close_database(db_connection)
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
    """
    Build a debug message for logging purposes.
    """
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


def check_file_permissions(path: str, apply_to_path: str) -> None:
    """
    Check the permissions of a file or directory and apply them to another.
    """
    root_permissions = os.stat("./").st_mode
    os.chmod(apply_to_path, root_permissions)
    if os.path.isdir(apply_to_path):
        for dirpath, dirnames, filenames in os.walk(apply_to_path):
            for dn in dirnames:
                os.chmod(os.path.join(dirpath, dn), root_permissions)
            for fn in filenames:
                os.chmod(os.path.join(dirpath, fn), root_permissions)


def check_function(
    path: str, create_dir: bool = False, is_directory: bool = True
) -> bool:
    """
    Check if a file or directory exists at the given path.
    """
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
            check_file_permissions("./", path)
            return True
        else:
            raise FileNotFoundError(f"Directory {path} does not exist")
    else:
        raise FileNotFoundError(f"File {path} does not exist")


def check_log_id_exists(db_connection: DatabaseConn, log_id: int) -> bool:
    """
    Check if a log ID exists in the database.
    """
    cursor = db_connection.cursor()
    try:
        if isinstance(db_connection, PostgresConn):
            cursor.execute("SELECT id FROM logger WHERE id = %s", (log_id,))
        elif type(db_connection) == SQLiteConn:
            cursor.execute("SELECT id FROM logger WHERE id = ?", (log_id,))
        else:
            raise Exception("Unsupported database connection type")

        if not cursor.fetchone():
            return False
        return True
    finally:
        cursor.close()


def close_database(connection) -> Optional[bool]:
    """
    Close the database connection.
    """
    try:
        connection.close()
        return True
    except Exception as e:
        raise Exception(f"[close_database({type(connection)}) failed]:{e}")


def connect_database(
    data_path: Optional[str] = None,
) -> Union[PostgresConn, SQLiteConn]:
    """
    Connect to the database using the provided credentials.
    """
    load_dotenv(find_dotenv(usecwd=True))

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
                "db_connect() called with LOGGER_MODE set to file."
            )
        else:
            raise Exception(f"{logger_mode} is either invalid or unsupported.")
    except Exception as e:
        err_1 = "[connect_database("
        err_2 = f"{os.getenv('DATABASE_MODE', '')}) failed]:{e}"
        raise Exception(err_1 + err_2)


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
                (level, source, log_notes, status, last_updated, internal)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    log_info.level,
                    log_info.source,
                    log_info.log_notes,
                    log_info.status,
                    get_timestamp_for_log(),
                    log_info.internal,
                ),
            )
        elif type(db_connection) == SQLiteConn:
            cursor.execute(
                """
                INSERT INTO logger
                (level, source, log_notes, status, last_updated, uuid, internal)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    log_info.level,
                    log_info.source,
                    log_info.log_notes,
                    log_info.status,
                    get_timestamp_for_log(),
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


def delete_log_admin(db_connection: DatabaseConn, log_id: int, uuid: str):
    """
    Delete a log entry from the database.
    """
    try:
        cursor = db_connection.cursor()
        if isinstance(db_connection, PostgresConn):
            cursor.execute(
                "DELETE FROM logger WHERE id = %s AND uuid = %s",
                (log_id, uuid),
            )
        elif type(db_connection) == SQLiteConn:
            cursor.execute(
                "DELETE FROM logger WHERE id = ? AND uuid = ?", (log_id, uuid)
            )
        else:
            raise Exception("Unsupported database connection type")

        db_connection.commit()
        cursor.close()
        return {"status": "success"}
    except Exception as e:
        cursor.close()
        close_database(db_connection)
        raise Exception(f"[delete_log_admin() failed]: {e}")


def dir_check(dir_path: str, create_dir: bool = True) -> bool:
    """
    Check if a directory exists at the given path.
    """
    return check_function(dir_path, create_dir, is_directory=True)


def fetch_log_path() -> str:
    """
    Fetch the path to the log file.
    """
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
    """
    Check if a file exists at the given path.
    """
    return check_function(file_path, is_directory=False)


def format_datetime(
    input_time: datetime, milliseconds: bool = False
) -> Optional[str]:
    """
    Format a datetime object to a string.
    """
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


def get_first_log_id(db_connection: DatabaseConn) -> int:
    """
    Fetch the first log ID in the database.
    """
    cursor = db_connection.cursor()
    try:
        if isinstance(db_connection, PostgresConn):
            cursor.execute("SELECT MIN(id) FROM logger")
        elif type(db_connection) == SQLiteConn:
            cursor.execute("SELECT MIN(id) FROM logger")
        else:
            raise Exception("Unsupported database connection type")

        result = cursor.fetchone()
        min_id = result[0] if result and result[0] is not None else 1
        return min_id
    finally:
        cursor.close()


def get_log_by_uuid(
    db_connection: DatabaseConn, uuid: str
) -> Optional[Dict[str, Any]]:
    """
    Fetch a log entry by UUID.
    """
    cursor = db_connection.cursor()
    try:
        if isinstance(db_connection, PostgresConn):
            cursor.execute(
                "SELECT id, uuid, log_notes, source, level, internal, datetime, last_updated FROM logger WHERE uuid = %s",
                (uuid,),
            )
        elif type(db_connection) == SQLiteConn:
            cursor.execute(
                "SELECT id, uuid, log_notes, source, level, internal, datetime, last_updated FROM logger WHERE uuid = ?",
                (uuid,),
            )
        else:
            raise Exception("Unsupported database connection type")
        log = cursor.fetchone()
        if log:
            return {
                "log_id": log[0],
                "uuid": log[1],
                "log_notes": log[2],
                "source": log[3],
                "level": log[4],
                "internal": json_to_string(log[5])[1] if log[5] else None,
                "datetime": (log[6]),
                "last_updated": ((log[7]) if log[7] else None),
            }
        else:
            raise HTTPException(status_code=404, detail="UUID not found")
    finally:
        cursor.close()


def get_new_log_id(db_connection: DatabaseConn) -> int:
    """
    Fetch the next available log ID.
    """
    cursor = db_connection.cursor()
    try:
        if isinstance(db_connection, PostgresConn):
            cursor.execute("SELECT MAX(id) FROM logger")
        elif type(db_connection) == SQLiteConn:
            cursor.execute("SELECT MAX(id) FROM logger")
        else:
            raise Exception("Unsupported database connection type")

        result = cursor.fetchone()
        max_id = result[0] if result and result[0] is not None else 0
        return max_id + 1
    finally:
        cursor.close()


def get_next_log_id(current_id: int, db_connection: DatabaseConn) -> int:
    """
    Fetch the next log ID after the current one, skipping logs with status 'deleted'.
    """
    cursor = db_connection.cursor()
    try:
        if isinstance(db_connection, PostgresConn):
            cursor.execute(
                "SELECT MIN(id) FROM logger WHERE id > %s AND status != 'deleted'",
                (current_id,),
            )
        elif type(db_connection) == SQLiteConn:
            cursor.execute(
                "SELECT MIN(id) FROM logger WHERE id > ? AND status != 'deleted'",
                (current_id,),
            )
        else:
            raise Exception("Unsupported database connection type")

        result = cursor.fetchone()
        next_id = result[0] if result and result[0] is not None else None
        if next_id is None:
            raise ValueError("No next log exists")
        return next_id
    finally:
        cursor.close()


def get_previous_log_id(current_id: int, db_connection: DatabaseConn) -> int:
    """
    Fetch the previous log ID before the current one, skipping logs with status 'deleted'.
    """
    cursor = db_connection.cursor()
    try:
        if isinstance(db_connection, PostgresConn):
            cursor.execute(
                "SELECT MAX(id) FROM logger WHERE id < %s AND status != 'deleted'",
                (current_id,),
            )
        elif type(db_connection) == SQLiteConn:
            cursor.execute(
                "SELECT MAX(id) FROM logger WHERE id < ? AND status != 'deleted'",
                (current_id,),
            )
        else:
            raise Exception("Unsupported database connection type")

        result = cursor.fetchone()
        previous_id = result[0] if result and result[0] is not None else None
        if previous_id is None:
            raise ValueError("No previous log exists")
        return previous_id
    finally:
        cursor.close()


def get_uuid_by_log_id(db_connection: DatabaseConn, log_id: int) -> str:
    """
    Fetch the UUID for a given log ID.
    """
    cursor = db_connection.cursor()
    try:
        if isinstance(db_connection, PostgresConn):
            cursor.execute("SELECT uuid FROM logger WHERE id = %s", (log_id,))
        elif type(db_connection) == SQLiteConn:
            cursor.execute("SELECT uuid FROM logger WHERE id = ?", (log_id,))
        else:
            raise Exception("Unsupported database connection type")

        uuid = cursor.fetchone()
        if uuid:
            return uuid[0] if uuid else ""
        else:
            raise HTTPException(status_code=404, detail="Log ID not found")
    finally:
        cursor.close()


def get_timestamp_for_log(milliseconds: bool = True) -> str:
    """
    Get the current timestamp for logging purposes.
    """
    return str(format_datetime(datetime.utcnow(), milliseconds))


def json_to_string(json_package: Dict[str, str]) -> Detailed_Result:
    """
    Convert a JSON package to a string.
    """
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
    """
    Validate a JSON package and convert it to a string if needed.
    """
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
    """
    Write a log message to a file.
    """
    wrap_text_at = 80
    today = str(get_timestamp_for_log(False)).split(" ")[0]
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


def new_log_entry(
    exception: Optional[Exception] = None,
    logging_msg: Optional[str] = None,
    logging_level: Optional[str] = None,
    source: Optional[str] = None,
    status: Optional[str] = "new",
    success: bool = False,
    console: bool = False,
    misc: Optional[str] = None,
) -> Union[bool, Detailed_Result]:
    """
    Create a new log entry in the database.
    """
    db_connection = None
    raw_dbinfo = [
        os.getenv("LOGGER_MODE", "file"),
        os.getenv("LOGGER_DIR", ".logs"),
        os.getenv("DATABASE_PATH", ":memory:"),
        os.getenv("DATABASE_USER", "root"),
        os.getenv("DATABASE_CRED", "password"),
        os.getenv("DATABASE_HOST", "localhost"),
        int(os.getenv("DATABASE_PORT", 5432)),
        os.getenv("DATABASE_NAME", "logger"),
    ]
    dbinfo = {
        "LOGGER_MODE": raw_dbinfo[0],
        "LOGGER_DIR": raw_dbinfo[1],
        "DATABASE_PATH": raw_dbinfo[2],
        "DATABASE_USER": raw_dbinfo[3],
        "DATABASE_CRED": raw_dbinfo[4],
        "DATABASE_HOST": raw_dbinfo[5],
        "DATABASE_PORT": raw_dbinfo[6],
        "DATABASE_NAME": raw_dbinfo[7],
    }
    if logging_level is None:
        logging_level = "ERROR" if exception else "INFO"
    if source is None:
        source = socket.getfqdn().lower()
    if (logging_level in ["INFO", "SUCCESS", "DEBUG"]) or (success):
        misc = misc if misc and len(misc) > 0 else None
    else:
        if misc and len(misc) > 0 and exception and str(exception).strip():
            misc = f"{misc}. Exception: {exception}"
        elif not misc and exception and str(exception).strip():
            misc = f"Exception: {exception}"
        elif misc and not (exception and str(exception).strip()):
            misc = f"{misc}. No exception provided."
        else:
            misc = f"No exception provided." if not misc else misc
    if dbinfo["LOGGER_MODE"] == "file":
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
                    misc = f"{misc}" if misc else None
                    complete_package = {
                        "level": logging_level,
                        "source": (
                            f"[{source.lower()}]"
                            if source
                            else f"[{socket.getfqdn().lower()}]"
                        ),
                        "log_notes": logging_msg,
                        "status": status.lower() if status else "new",
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
                    "source": (
                        f"[{source.lower()}]"
                        if source
                        else f"[{socket.getfqdn().lower()}]"
                    ),
                    "log_notes": logging_msg,
                    "status": status.lower() if status else "new",
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
                dbpath = dbinfo["DATABASE_PATH"] if dbinfo else None
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


def set_key(file_path, key, value):
    """
    Set a key-value pair in a file.
    """
    with open(file_path, "r") as f:
        lines = f.readlines()
    with open(file_path, "w") as f:
        for line in lines:
            if line.startswith(key):
                line = f"{key}={value}\n"
            f.write(line)


def set_log_to_deleted(db_connection: DatabaseConn, log_id: int, uuid: str):
    """
    Update a log entry to a deleted status.
    """
    try:
        if not db_connection:
            raise HTTPException(
                status_code=500, detail="Failed to connect to database"
            )
        existing_log = get_log_by_uuid(db_connection, uuid)
        if not existing_log:
            raise HTTPException(status_code=404, detail="Log entry not found")

        current_notes = existing_log.get("log_notes")
        current_source = existing_log.get("source")
        current_level = existing_log.get("level")
        current_internal = existing_log.get("internal", "")

        success = update_db_log_by_uuid(
            uuid=uuid,
            logging_msg=current_notes,
            logging_level=current_level,
            source=current_source,
            status="deleted",
            misc=current_internal,
        )
        if success:
            return {
                "status": "success",
                "message": "Log status set to deleted.",
            }
        else:
            raise Exception("Failed to update log entry.")

    except HTTPException as he:
        return {"status": he.status_code, "message": he.detail}
    except Exception as e:
        new_log_entry(e, "Failed to set log to deleted", "CRITICAL")
        return {"status": "failure", "message": str(e)}
    finally:
        close_database(db_connection)


def string_validator(string: str, clean: bool = True) -> Detailed_Result:
    """
    Validate a string and return a cleaned version if requested.
    """
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
    """
    Substitute characters in a string with Unicode characters.
    """
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


def update_db_log_by_uuid(
    uuid: str,
    logging_msg: Optional[str],
    logging_level: Optional[str],
    source: Optional[str],
    status: Optional[str],
    misc: Optional[str],
) -> bool:
    """
    Update an existing log entry in the database logger by UUID.
    """
    db_connection = None
    cursor = None
    misc_check = misc
    if misc_check is not None and misc_check.lower().startswith("misc:"):
        misc_check = misc_check[5:]
    if misc_check is not None:
        formatted_misc = {"misc": misc_check}
        misc_validated = json_validator(formatted_misc, False)
        if misc_validated[0]:
            misc = json.dumps(misc_validated[1])
    try:
        db_connection = connect_database()
        cursor = db_connection.cursor()
        if isinstance(db_connection, PostgresConn):
            update_string = "SET level = %s, source = %s, log_notes = %s, status = %s, last_updated = %s"
            if misc:
                update_string += ", internal = %s"
            cursor.execute(
                f"UPDATE logger {update_string} WHERE uuid = %s",
                (
                    (
                        logging_level,
                        source,
                        logging_msg,
                        status,
                        get_timestamp_for_log(),
                        misc,
                        uuid,
                    )
                    if misc
                    else (
                        logging_level,
                        source,
                        logging_msg,
                        status,
                        get_timestamp_for_log(),
                        uuid,
                    )
                ),
            )
        elif type(db_connection) == SQLiteConn:
            update_string = "SET level = ?, source = ?, log_notes = ?, status = ?, last_updated = ?"
            if misc:
                update_string += ", internal = ?"
            cursor.execute(
                f"UPDATE logger {update_string} WHERE uuid = ?",
                (
                    (
                        logging_level,
                        source,
                        logging_msg,
                        status,
                        get_timestamp_for_log(),
                        misc,
                        uuid,
                    )
                    if misc
                    else (
                        logging_level,
                        source,
                        logging_msg,
                        status,
                        get_timestamp_for_log(),
                        uuid,
                    )
                ),
            )

        else:
            raise Exception(
                f"Invalid database mode: {os.environ['LOGGER_MODE']}"
            )
        db_connection.commit()
        cursor.close() if cursor else None
        close_database(db_connection) if db_connection else None
        return True
    except Exception as e:
        cursor.close() if cursor else None
        close_database(db_connection) if db_connection else None
        error_message = build_debug_message(
            level=logging_level,
            log_notes=logging_msg,
            source=source,
            status=status,
            internal=misc,
        )
        logger_x.critical(
            f"[update_db_log_by_uuid({type(db_connection)}) failed]\n"
            f"[uuid]:{uuid}\n"
            f"[Exception]:{e}\n\n"
            f"[Detailed Info]:\n{error_message}"
        )
        return False


def webgui_check() -> bool:
    """
    Check the webgui configuration and update the package.json file with the
    necessary environment variables.
    """
    try:
        logging.debug("Checking webgui configuration...")
        webgui_path = "./webgui"
        root_env_path = "./.env"
        package_json_path = os.path.join(webgui_path, "package.json")

        if not dir_check(webgui_path):
            raise FileNotFoundError(
                "Webgui directory not found and is required."
            )
        logging.debug(f"Directory checked: {webgui_path}")

        if not file_exists(root_env_path):
            raise FileNotFoundError("Root .env file not found.")

        root_env = dotenv_values(root_env_path)
        logging.debug(f"Loaded environment variables from {root_env_path}")

        https_value = "false"
        web_port = "3000"
        api_url = "localhost"
        api_port = "5000"
        secret_key = ""

        if root_env.get("WEB_PORT"):
            web_port = root_env["WEB_PORT"]
        if root_env.get("API_URL"):
            api_url = root_env["API_URL"]
        if root_env.get("API_PORT"):
            api_port = root_env["API_PORT"]
        if root_env.get("SECRET_KEY"):
            secret_key = f"REACT_APP_SECRET_KEY={root_env['SECRET_KEY']} "
        if root_env.get("SSL_CRT_FILE") and root_env.get("SSL_KEY_FILE"):
            https_value = "true"

        start_command = (
            f"REACT_APP_API_URL={api_url} "
            f"REACT_APP_API_PORT={api_port} "
            f"{secret_key}"
            f"REACT_APP_MILITARY_TIME={root_env.get('MILITARY_TIME', 'false')} "
            f"PORT={web_port} HTTPS={https_value} "
            f"SSL_CRT_FILE={root_env.get('SSL_CRT_FILE', '')} "
            f"SSL_KEY_FILE={root_env.get('SSL_KEY_FILE', '')} "
            f"react-scripts start"
        )

        if file_exists(package_json_path):
            with open(package_json_path, "r") as file:
                package_json = json.load(file)
            package_json["scripts"]["start"] = start_command
            with open(package_json_path, "w") as file:
                json.dump(package_json, file, indent=4)
            logging.debug("Updated package.json with the new start command.")
        else:
            raise FileNotFoundError(
                "package.json not found in the webgui directory."
            )

        check_file_permissions(root_env_path, webgui_path)
        logging.info("Webgui configuration check completed successfully.")

        return True
    except Exception as e:
        logging.error(f"Failed to check webgui configuration: {e}")
        raise Exception(f"[webgui_check() failed]: {e}")


if __name__ == "__main__":
    try:
        if not os.path.isfile(".env"):
            raise FileNotFoundError(
                ".env file not found. Please create a .env file."
            )
        else:
            webgui_check()

        load_dotenv(find_dotenv(usecwd=True))

        parser = argparse.ArgumentParser(
            description="Logger_X Server by CNB, LLC v1.1.0"
        )
        parser.add_argument(
            "-b",
            "--build",
            help="Build new database on db server defined in .env",
            action="store_true",
        )
        parser.add_argument(
            "-a",
            "--add",
            help="Log a new entry (json with msg, lvl, success, misc).",
            type=json.loads,
        )
        parser.add_argument(
            "-u",
            "--update",
            help=(
                "Update a log entry by UUID. Requires JSON input with 'uuid' and "
                "at least one of the following fields: 'logging_msg', 'logging_level', "
                "'source', 'status', 'misc'. Example: '{\"uuid\": \"entry-uuid\", "
                '"status": "new-status"}\''
            ),
            type=json.loads,
        )
        parser.add_argument(
            "-l",
            "--listener",
            help="Start API Listener (for custom use args -i -p -s)",
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
        parser.add_argument(
            "-n",
            "--nossl",
            help="Start API Listener without SSL",
            action="store_true",
        )

        args = parser.parse_args()

        if args.build:
            try:
                new_connection = connect_database()
                if new_connection:
                    create_new_database(new_connection)
                    close_database(new_connection)
                    print("Database created successfully.")
                else:
                    raise Exception("Failed to connect to database.")
            except Exception as e:
                raise Exception(f"Failed to create database: {e}")
        elif args.add:
            new_log_entry(**args.add)
        elif args.update:
            update_data = args.update
            if "uuid" not in update_data:
                raise ValueError("Error: 'uuid' is required.")
            if any(
                k in update_data
                for k in [
                    "logging_msg",
                    "logging_level",
                    "source",
                    "status",
                    "misc",
                ]
            ):
                success = update_db_log_by_uuid(
                    uuid=update_data.get("uuid"),
                    logging_msg=update_data.get("logging_msg"),
                    logging_level=update_data.get("logging_level"),
                    source=update_data.get("source"),
                    status=update_data.get("status"),
                    misc=update_data.get("misc"),
                )
                if success:
                    print("Log entry updated successfully.")
                else:
                    raise Exception("Failed to update log entry.")
            else:
                raise ValueError(
                    "Error: At least one field to update must be specified."
                )
        elif args.listener:
            ip = "0.0.0.0"
            port = 8000
            ssl = None
            if args.ip:
                ip = args.ip
            else:
                ip = os.getenv("API_HOST", "0.0.0.0")
            if args.port:
                port = args.port
            else:
                port = int(os.getenv("API_PORT", 8000))
            if args.nossl:
                ssl = None
            else:
                if args.ssl:
                    ssl = args.ssl
                else:
                    ssl = None
            api_listener(ip, port, ssl)
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
