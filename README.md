# Logger by GDV, LLC

- **Version**: v1.0.0
- **Date**: 11.29.2023 @ 11:38 AM PST
- **Written by**: Geoff Clark of GDV, LLC

Logger is a comprehensive logging tool designed for robust and flexible logging in Python applications. It supports both file-based and database-based logging, with features for creating, updating, and managing log entries. Additional functionalities include an API listener for receiving log data, and planned features for a console interface and GUI.

## Getting Started

These instructions will get you a copy of the project up and running on your local machine for development and testing purposes.

## Prerequisites

- Python 3.x
- Additional Python packages: `argparse`, `psycopg2`, `uvicorn`, `fastapi`, `pydantic`, etc.

## Installation

Clone the repository and install the required packages:

```bash
git clone https://github.com/AznIronMan/logger
cd logger
```

(Automated) - Installs Python 3.12 (if needed), creates a virtual environment, installs the required packages, and builds logger_helper launcher.
```bash
./install.sh    # Mac or Linux (be sure to chmod +x)
./install.bat   # Windows
```

(for first time help use) - Explains how to launch the logger.py helper menu.
```bash
./logger_helper.sh  # Mac or Linux (be sure to chmod +x)
./logger_helper.bat # Windows
```

(Manual) - Installs the required packages. (This assumes you have Python 3.11 or 3.12 *recommended* installed)
```bash
pip install -r requirements.txt
```

## Usage

This utility can be used in several modes: adding a log entry, updating an entry, launching a GUI or console (future implementation), and starting an API listener.

```bash
python logger.py --help   # Display usage information and args
```

logger.py can be used as a standalone utility or imported as a module. All functions were built in the single file for ease of use and deployment.

### Adding a Log Entry

```bash
python logger.py -a '{"logging_msg": "Your log message", "logging_level": "INFO"}'
```

### Updating a Log Entry

```bash
python logger.py -u '{"uuid": "entry-uuid", "status": "new-status"}'
```

### Starting the API Listener

```bash
python logger.py -l
```

Note: Detailed usage for each feature will be provided as these are implemented.

## Future Features

- Console and GUI interfaces (all OS supported -- GUI using PyQt6)
- Interactive API Management in interface
- Advanced log management (search, export, updating, etc.) in interface
- Support for MySQL, Mongo, Redis, and other databases
- AI and ML integration for log analysis and anomaly detection

## Author Information

- **Author**: [Geoff Clark of GDV, LLC](https://clarktribegames.com)
- **Email**: [geoff@gdv.llc](mailto:geoff@gdv.llc)
- **Socials**:
  [GitHub @aznironman](https://github.com/aznironman)
  [IG: @aznironman](https://instagram.com/aznironman)
  [Twitter: @aznironman](https://www.twitter.com/aznironman)

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Third-Party Notices

All rights reserved by their respective owners. Users must comply with the licenses and terms of service of the software being installed.