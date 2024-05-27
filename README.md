# Logger_X Server by Clark & Burke, LLC

- **Version**: v1.2.1
- **Date**: 05.27.2024 @ 09:35 AM PST
- **Written by**: Geoff Clark of Clark & Burke, LLC

- **README.md Last Updated**: 05.27.2024

Logger_X Server is a comprehensive logging tool designed for robust and flexible logging in Python applications. It supports both file-based and database-based logging, with features for creating, updating, and managing log entries. Additional functionalities include an API listener for receiving log data, and planned features for a console interface and GUI.

## Getting Started

These instructions will get you a copy of the project up and running on your local machine for development and testing purposes.

## Prerequisites

- Python 3.10 or higher
- Additional Python packages: `argparse`, `psycopg2`, `uvicorn`, `fastapi`, `pydantic`, etc.

## Installation

Clone the repository and install the required packages:

```bash
git clone https://github.com/AznIronMan/logger_x
cd logger
```

(Automated) - Installs Python 3.12 (if needed), creates a virtual environment, installs the required packages, and builds logger_helper launcher.

```bash
./install.sh    # Mac or Linux (be sure to chmod +x)
./install.bat   # Windows
```

(for first time help use) - Explains how to launch the logger_x.py helper menu.

```bash
./logger_helper.sh  # Mac or Linux (be sure to chmod +x)
./logger_helper.bat # Windows
```

(Manual) - Installs the required packages. (This assumes you have Python 3.11 or 3.12 _recommended_ installed)

```bash
pip install -r requirements.txt
```

## Usage

This utility can be used in several modes: adding a log entry, updating an entry, launching a GUI or console (future implementation), and starting an API listener.

```bash
python logger_x.py --help   # Display usage information and args
```

logger_x.py can be used as a standalone utility or imported as a module. All functions were built in the single file for ease of use and deployment.

### Adding a Log Entry

```bash
python logger_x.py -a '{"logging_msg": "Your log message", "logging_level": "INFO"}'
```

### Updating a Log Entry

```bash
python logger_x.py -u '{"uuid": "entry-uuid", "status": "new-status"}'
```

### Starting the API Listener

```bash
python logger_x.py -l
```

## Web GUI

The Logger_X Server now includes a web GUI for easier log management. The frontend is built with React, and the backend uses FastAPI. To run the web GUI:

1. Ensure you have the necessary environment variables set in your `.env` file.
2. Navigate to the `webgui` directory and install the required packages:

   ```bash
   cd webgui
   npm install
   ```

3. Start the web GUI:
   ```bash
   npm start
   ```

### Environment Variables

The following environment variables are required for the web GUI:

- `HTTPS` (boolean, manual, should mirror if .env has SSL cert/key defined or not)
- `REACT_APP_API_URL`
- `REACT_APP_API_PORT`
- `REACT_APP_SECRET_KEY`
- `REACT_APP_MILITARY_TIME` (optional, default is `false`)

## Completed Features

- File-based logging
- Database-based logging (PostgreSQL/SQLite)
- CLI for adding and updating log entries
- API listener for receiving log data
- Web GUI for log management
- Automated installation script
- Automated virtual environment creation
- Automated launcher creation

## Future Features

- Console and GUI interfaces (all OS supported -- GUI using PyQt6)
- Interactive API Management in interface
- Advanced log management (search, export, updating, etc.) in interface
- Support for MySQL, Mongo, Redis, and other databases
- AI and ML integration for log analysis and anomaly detection

## Update Notes

### Version 1.2.1 - 05.27.2024 @ 09:35 AM PST

- Fixed `create_db_log()` not having the proper number of parameters for DB writing.
- Added `logger_x_table_name` variable.
- Added HTTP/HTTPS variable for flexibility and auto-adjustment based on `.env` (for backend) and frontend will look at `https=boolean` in the `npm start` in `package.json` for adjustment.
- Fixed `create_database()` not working and added `table_exists()` function.
- Updated the listener CLI argument to include a check if the table exists and if not, create it.

## Author Information

- **Author**: [Geoff Clark of Clark & Burke, LLC](https://www.cnb.llc)
- **Email**: [geoff@cnb.llc](mailto:geoff@cnb.llc)
- **Socials**:
  [GitHub @aznironman](https://github.com/aznironman)
  [IG: @cnbllc](https://instagram.com/cnbllc)
  [X: @clarkandburke](https://www.x.com/clarkandburke)

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Third-Party Notices

All rights reserved by their respective owners. Users must comply with the licenses and terms of service of the software being installed.
