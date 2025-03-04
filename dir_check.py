import os
import re


current_dir = os.getcwd()
print("當前工作目錄：", current_dir)






# 變更目錄
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# 目前目錄
dir_now = os.getcwd()
print("變更後目錄：", dir_now)

