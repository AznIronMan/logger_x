#!/bin/bash
echo "Starting Logger by GDV, LLC Installer..."
echo
if [[ $EUID -ne 0 ]]; then
    echo "ERROR: This script requires administrative privileges. Please run as root or with sudo."
    exit 1
fi
install_wget() {
    echo "wget not found, attempting to install..."
    echo
    case "$1" in
        "apt-get")
            sudo apt-get update
            sudo apt-get install -y wget
            ;;
        "yum")
            sudo yum install -y wget
            ;;
        "dnf")
            sudo dnf install -y wget
            ;;
        "brew")
            brew install wget
            ;;
        *)
            echo "ERROR: Package manager not supported. Please install wget manually."
            exit 1
            ;;
    esac
    if command -v wget >/dev/null 2>&1; then
        echo "SUCCESS: wget installed successfully."
        echo
    else
        echo "ERROR: Failed to install wget. Please install it manually."
        echo
        exit 1
    fi
}
if ! command -v wget >/dev/null 2>&1; then
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        if [[ -f /etc/debian_version ]]; then
            install_wget "apt-get"
        elif [[ -f /etc/redhat-release ]]; then
            if command -v dnf >/dev/null 2>&1; then
                install_wget "dnf"
            else
                install_wget "yum"
            fi
        else
            echo "ERROR: Unsupported Linux distribution. Please install wget manually."
            echo
            exit 1
        fi
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        if command -v brew >/dev/null 2>&1; then
            install_wget "brew"
        else
            echo "ERROR: Homebrew is not installed. Please install Homebrew or wget manually."
            echo
            exit 1
        fi
    else
        echo "ERROR: Unsupported operating system. Please install wget manually."
        echo
        exit 1
    fi
fi
check_and_install_python() {
    local python_version=$(python3 --version 2>&1)
    local min_python_version="3.11."
    local target_python_version="3.12."
    local python_found=false

    if [[ $python_version == *"$min_python_version"* ]] || [[ $python_version == *"$target_python_version"* ]]; then
        python_found=true
    fi

    if [[ $python_found == false ]]; then
        echo "Suitable version of Python not found."
        echo 
        read -p "Do you want to download and install Python 3.12? [Y/N]: " install_python
        if [[ ${install_python,,} != "y" ]]; then
            echo "ERROR: Python 3.11.x or Python 3.12.x is required. Exiting."
            echo
            exit 1
        fi
        echo "Downloading Python 3.12..."
        echo
        mkdir -p ./.installer-temp
        wget -P ./.installer-temp/ https://www.python.org/ftp/python/3.12.0/Python-3.12.0.tgz
        echo "Installing Python 3.12..."
        echo
        mkdir -p ./.installer-temp/python312
        tar -xzf ./.installer-temp/Python-3.12.0.tgz -C ./.installer-temp/python312 --strip-components=1
        ./.installer-temp/python312/configure --prefix=$(pwd)/.venv/python312
        make -C ./.installer-temp/python312
        make -C ./.installer-temp/python312 install
        if [[ ! -f ./.venv/python312/bin/python3 ]]; then
            echo "ERROR: Failed to install Python 3.12. Try manually installing Python 3.12 and run this script again."
            echo
            exit 1
        else
            echo "SUCCESS: Python 3.12 installed successfully."
            echo
        fi
    fi
}
check_and_install_python
if [[ ! -d ./.venv/bin ]]; then
    ./.venv/python312/bin/python3 -m venv .venv
    echo "SUCCESS: Virtual environment created successfully."
    echo
fi
source ./.venv/bin/activate
if [[ -z "$VIRTUAL_ENV" ]]; then
    echo "ERROR: Failed to activate virtual environment. Try removing the .venv folder and try this script again."
    echo
    exit 1
fi
if [[ -x logger_help.sh ]]; then
    echo "SUCCESS: Everything looks good. You can run 'logger_help.bat' to begin logger helper."
    echo "Run 'logger_help.sh' to begin logger helper."
    echo
fi
echo "Using virtual environment: $VIRTUAL_ENV"
echo
python3 -m pip install --upgrade pip
pip install -r requirements.txt
pip list | grep icecream &>/dev/null
if [[ $? -eq 0 ]]; then
    echo "#!/bin/bash" > logger_help.sh
    echo "source ./.venv/bin/activate" >> logger_help.sh
    echo "echo use 'python .\logger.py --help' to launch with args helper" >> logger_help.sh
    chmod +x logger_help.sh
    if [[ -x logger_help.sh ]]; then
        echo "SUCCESS: Logger server installed successfully."
        echo "Run 'logger_help.sh' to begin logger helper."
    else
        echo "ERROR: Could not create or execute logger_help.sh."
        exit 1
    fi
else
    echo "ERROR: icecream package is not installed, could not complete installation. Please try again."
    exit 1
fi

exit 0