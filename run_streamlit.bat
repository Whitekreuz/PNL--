@echo off
cd /d "%~dp0"
D:\miniconda3\envs\quant\python.exe -m streamlit run app.py > streamlit.log 2>&1
