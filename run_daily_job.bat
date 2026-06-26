@echo off
echo [%date% %time%] Starting daily job... > daily_job.log
D:\miniconda3\envs\quant\python.exe daily_job.py >> daily_job.log 2>&1
echo [%date% %time%] Done. >> daily_job.log
