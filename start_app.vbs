Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "d:\datasci\PNL日志"
WshShell.Run "D:\miniconda3\envs\quant\python.exe -m streamlit run app.py", 0, False
