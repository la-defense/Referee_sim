@echo off
rem 打包 RefereeSim.exe（需先 pip install pyinstaller）
cd /d %~dp0
python -m PyInstaller --noconfirm --clean RefereeSim.spec
echo 产物: dist\RefereeSim.exe
