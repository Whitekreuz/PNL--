import subprocess
import os
import sys

base_dir = os.path.dirname(os.path.abspath(__file__))
app_path = os.path.join(base_dir, "app.py")
python_exe = r"D:\miniconda3\envs\quant\python.exe"

# Launch streamlit in a detached process
CREATE_NO_WINDOW = 0x08000000
DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200
subprocess.Popen([python_exe, "-m", "streamlit", "run", app_path], 
                 cwd=base_dir,
                 creationflags=CREATE_NO_WINDOW | DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                 close_fds=True)
