
# 🛠️ ALP'S Toolkit

A collection of utilities for Teltonika device development, built with Streamlit and Python.

## Features

- **📡 GPS Server**: Real-time TCP/UDP listener for Teltonika GPS devices (Codec 8/8E/12/13), live data feed, parsing, and command sending.
- **🔍 Log Parser**: Parse Teltonika Catcher logs (.clg, .txt), visualize connection events, extract AT commands, and map GPS points.
- **🔌 COM Unlocker**: Identify and kill processes locking COM ports, restart device drivers.
- **⏱️ Jira Tracker**: Log work to Jira tickets, standup mode, progress bars, open local folders.
- **🚀 Release Creator**: Wizard for creating new firmware versions in Jira, auto-generates release tickets.
- **Universal Tester Tool**: Integrates with external test scripts and databases.
- **Serial Port Monitor**: Monitor and debug local serial (COM) ports.
- **Extensible Plugin Architecture**: Easily add new tools via the `app/plugins/` directory.

## Installation

1. **Clone the repository**:
   ```bash
   git clone
   cd alps-toolkit
   ```
2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

## Usage

### Option 1: System Tray (Windows)
Start the toolkit in the background with a system tray icon:
```bash
python streamlit_tray.py
```
Or double-click `start_alps_toolkit.vbs`.

### Option 2: Direct Launch
Run Streamlit directly in your terminal:
```bash
streamlit run run.py
```
Or run `python run.py` if your entry point is set up accordingly.

## Configuration
- **Toolkit settings**: `toolkit_settings.json` (auto-created/managed).
- **Jira credentials**: `jira-time-tracker/jira_config.json`.

## Project Structure

```
.
├── app/
│   ├── main.py
│   ├── config.py
│   └── plugins/
│       ├── base.py
│       ├── com_unlocker.py
│       ├── gps_server.py
│       ├── jira_tracker.py
│       ├── log_parser.py
│       ├── release_creator.py
│       └── universal_tester_tool.py
├── modules/
│   ├── easy_catcher_adapter.py
│   ├── gps_codes.py
│   ├── server_singleton.py
│   └── utils.py
├── jira-time-tracker/
│   ├── streamlit_app.py
│   ├── streamlit_tray.py
│   └── jira_config.json
├── atcmd-parser/
│   └── atcmd.py
├── com-killer/
│   └── comkiller.py
├── easy-catcher/
│   ├── easy_catcher.py
│   └── config.yml
├── universal-tester-tool/
│   └── launcher.py
├── run.py
├── tray_launcher.py
├── requirements.txt
├── toolkit_settings.json
└── README.md
```

## Development

- Add new plugins in `app/plugins/`.
- Extend core logic in `app/` and `modules/` as needed.
- Use `requirements.txt` to manage dependencies.

## Troubleshooting

- **Port in use**: Ensure no other app is using the same port.
- **Permissions**: Run as administrator if needed for COM port access.
- **Missing config**: Required config files are auto-created on first run or can be copied from `.dist` templates.

## Contributing

Contributions are welcome! Please submit a Pull Request.