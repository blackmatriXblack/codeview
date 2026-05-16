@echo off
echo ==========================================
echo   CodeView CLI v3.0 - Installation
echo ==========================================
echo.

REM Check for Python
where python >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Python is not installed or not in PATH.
    echo Please install Python 3.9+ from https://python.org
    pause
    exit /b 1
)

echo [INFO] Python found: 
python --version
echo.

echo [INFO] Installing CodeView CLI...
pip install -e .
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Installation failed.
    pause
    exit /b 1
)

echo.
echo ==========================================
echo   Installation Complete!
echo ==========================================
echo.
echo Usage:
echo   codeview ^<file^>          View a file with highlighting
echo   codeview ^<url^>           Fetch and view code from a repo
echo   codeview edit              Open the TUI editor (Textual)
echo   codeview edit --curses     Open the curses editor (Vim-mode)
echo   codeview tree              Browse directory tree
echo   codeview search ^<q^>      Search text in files
echo   codeview snippets          Code snippet library
echo   codeview history           File open history
echo   codeview notes             Quick notes manager
echo   codeview hex ^<file^>       Hex dump viewer
echo   codeview hash ^<file^>      File hash / checksum
echo   codeview base64 encode/decode  Base64 tools
echo   codeview watch ^<dir^>      Watch for file changes
echo   codeview serve ^<dir^>      HTTP server
echo   codeview colors            Color palette
echo   codeview git-log           Git log viewer
echo   codeview bookmark          Manage shortcuts
echo   codeview project           Project management
echo   codeview md ^<file^>        Render Markdown
echo   codeview themes            List color themes
echo   codeview --help            Show all commands
echo.
echo Aliases: codeview, cv
echo.
pause
