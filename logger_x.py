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
import stat
import sys
import textwrap
import traceback
import uvicorn
import uuid

from collections import namedtuple
from datetime import datetime
from dotenv import dotenv_values, find_dotenv, load_dotenv, set_key
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from rich.console import Console
from rich.logging import RichHandler
from pydantic import BaseModel, Field
from typing import Any, Dict, NewType, Optional, Sequence, Tuple, Union


# TODO: Add docstrings to all functions and classes
# TODO: Implement the create_new_database() function
# TODO: look at file_exists(), dir_check(), fetch_log_path(), format_datetime(),
#      get_database_info(), convert_sequence_to_dict(), revert_characters(),
#      substitute_characters() for use cases or removal

# TODO: add check if webgui folder exists, if so, check for env, if not create env (function)

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

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Allows all origins
        allow_credentials=True,
        allow_methods=["*"],  # Allows all methods
        allow_headers=["*"],  # Allows all headers
    )

    load_dotenv(find_dotenv(usecwd=True))

    def verify_secret_key(x_secret_key: str = Header(...)):
        if x_secret_key != os.getenv("SECRET_KEY"):
            raise HTTPException(status_code=403, detail="Invalid secret key")

    @app.post("/add")
    async def api_add_entry(
        entry: NewDBEntry, secret_key: str = Depends(verify_secret_key)
    ):
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

    @app.post("/update/")
    async def api_update_entry(
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

    @app.get("/firstlogid")
    async def api_first_log_id(secret_key: str = Depends(verify_secret_key)):
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
        try:
            db_connection = connect_database()
            try:
                next_id = get_next_log_id(current_id, db_connection)
                return {"next_log_id": next_id}
            except ValueError as ve:  # Handle the case where no next ID exists
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
        try:
            db_connection = connect_database()
            try:
                previous_id = get_previous_log_id(current_id, db_connection)
                return {"previous_log_id": previous_id}
            except (
                ValueError
            ) as ve:  # Handle the case where no previous ID exists
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
    try:
        connection.close()
        return True
    except Exception as e:
        raise Exception(f"[close_database({type(connection)}) failed]:{e}")


def connect_database(
    data_path: Optional[str] = None,
) -> Union[PostgresConn, SQLiteConn]:
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


def delete_log_admin(
    db_connection: DatabaseConn, log_id: int, uuid: str
) -> bool:
    cursor = db_connection.cursor()
    if isinstance(db_connection, PostgresConn):
        cursor.execute(
            "DELETE FROM logger WHERE id = %s AND uuid = %s", (log_id, uuid)
        )
    elif type(db_connection) == SQLiteConn:
        cursor.execute(
            "DELETE FROM logger WHERE id = ? AND uuid = ?", (log_id, uuid)
        )
    else:
        raise Exception("Unsupported database connection type")

    db_connection.commit()
    cursor.close()
    return True


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
    load_dotenv(find_dotenv(usecwd=True))
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


def get_first_log_id(db_connection: DatabaseConn) -> int:
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
    cursor = db_connection.cursor()
    try:
        if isinstance(db_connection, PostgresConn):
            cursor.execute(
                "SELECT id, uuid, log_notes, source, level, internal FROM logger WHERE uuid = %s",
                (uuid,),
            )
        elif type(db_connection) == SQLiteConn:
            cursor.execute(
                "SELECT id, uuid, log_notes, source, level, internal FROM logger WHERE uuid = ?",
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
                "internal": log[5],
            }
        else:
            raise HTTPException(status_code=404, detail="UUID not found")
    finally:
        cursor.close()


def get_new_log_id(db_connection: DatabaseConn) -> int:
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
    cursor = db_connection.cursor()
    try:
        if isinstance(db_connection, PostgresConn):
            cursor.execute(
                "SELECT MIN(id) FROM logger WHERE id > %s", (current_id,)
            )
        elif type(db_connection) == SQLiteConn:
            cursor.execute(
                "SELECT MIN(id) FROM logger WHERE id > ?", (current_id,)
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
    cursor = db_connection.cursor()
    try:
        if isinstance(db_connection, PostgresConn):
            cursor.execute(
                "SELECT MAX(id) FROM logger WHERE id < %s", (current_id,)
            )
        elif type(db_connection) == SQLiteConn:
            cursor.execute(
                "SELECT MAX(id) FROM logger WHERE id < ?", (current_id,)
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
        load_dotenv(find_dotenv(usecwd=True))
        if new_info is None:
            new_info = get_env()
        if new_info.LOGGER_MODE in other_supported:
            keys_to_set = ["LOGGER_MODE", "LOGGER_DIR"]
        elif new_info.LOGGER_MODE in supported_servers:
            keys_to_set = [
                "LOGGER_MODE",
                "LOGGER_DIR",
                "DATABASE_USER",
                "DATABASE_CRED",
                "DATABASE_HOST",
                "DATABASE_PORT",
                "DATABASE_NAME",
            ]
        elif new_info.LOGGER_MODE in supported_file_db:
            keys_to_set = ["LOGGER_MODE", "LOGGER_DIR", "DATABASE_PATH"]
        else:
            logger_x.warning(
                "Invalid LOGGER_MODE, defaulting to file as LOGGER_MODE"
            )
            new_info = new_info._replace(logger_mode="file")
            keys_to_set = ["LOGGER_MODE", "LOGGER_DIR"]
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


def set_log_to_deleted(db_connection: DatabaseConn, log_id: int, uuid: str):
    try:
        if not db_connection:
            raise HTTPException(
                status_code=500, detail="Failed to connect to database"
            )
        existing_log = get_log_by_uuid(db_connection, uuid)
        if not existing_log:
            raise HTTPException(status_code=404, detail="Log entry not found")
        update_values = {
            "uuid": uuid,
            "status": "resolved",
            "status_notes": existing_log.get("status_notes", ""),
            "internal": existing_log.get("internal", ""),
        }
        update_db_log(db_connection, uuid, **update_values)
        return {"status": "success", "message": "Log status set to deleted."}
    except HTTPException as he:
        return {"status": he.status_code, "message": he.detail}
    except Exception as e:
        new_log_entry(e, "Failed to set log to deleted", "CRITICAL")
        return HTTPException(status_code=500, detail=str(e))
    finally:
        close_database(db_connection)


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


def webgui_check() -> None:
    keys_to_check = ["API_PORT", "SECRET_KEY"]

    webgui_path = "./webgui"
    env_path = os.path.join(webgui_path, ".env")
    root_env_path = "./.env"

    dir_check(webgui_path)

    if file_exists(root_env_path):
        root_env = dotenv_values(root_env_path)
    else:
        raise FileNotFoundError("Root .env file not found.")

    if not os.path.isfile(env_path):
        with open(env_path, "w") as f:
            for key in keys_to_check:
                if key in root_env:
                    f.write(f"{key}={root_env[key]}\n")
        check_file_permissions(
            root_env_path, env_path
        )  # Set permissions for new .env file
    else:
        env_values = dotenv_values(env_path)
        for key in keys_to_check:
            if env_values.get(key) != root_env.get(key):
                set_key(env_path, key, root_env.get(key) or "")
        check_file_permissions(root_env_path, env_path)


if __name__ == "__main__":
    try:
        # if not os.path.isfile(".env"):
        #     raise FileNotFoundError(
        #         ".env file not found. Please create a .env file."
        #     )
        # else:
        #     webgui_check()

        load_dotenv(find_dotenv(usecwd=True))

        parser = argparse.ArgumentParser(
            description="Logger_X Server by CNB, LLC v1.1.0"
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
            help="Update a log entry (json with uuid, status, notes, internal).",
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

        if args.add:
            new_log_entry(**args.add)
        elif args.update:
            update_db_log(**args.update)
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
