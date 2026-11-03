@echo off
rem T2-09 子项③ VM 容量偏差复测 · guest 驱动脚本（headless，guestcontrol run 承载）
rem UTF-8 双保险 = T-01 退回单教训（PYTHONUTF8=1 + PYTHONIOENCODING=utf-8）
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
cd /d C:\stage\t209c
powershell -NoProfile -ExecutionPolicy Bypass -File build_baseline.ps1 > ps_baseline_out.txt 2> ps_baseline_err.txt
echo PS_RC=%ERRORLEVEL%
C:\stage\python-3.13.5\python.exe tools\check_size_deviation.py --baseline baseline_vm.json > baseline_out.txt 2> baseline_err.txt
echo BASELINE_RC=%ERRORLEVEL%
C:\stage\python-3.13.5\python.exe tools\check_size_deviation.py --fixture > fixture_out.txt 2> fixture_err.txt
echo FIXTURE_RC=%ERRORLEVEL%
