# init.py
import subprocess
import time
import sys
import os

MAX_CRASHES = 3          # 最大连续崩溃重试次数
RESTART_EXIT_CODE = 42   # 定义特殊的退出码，表示“正常热重启”

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] 👑 {msg}", flush=True)

def main():
    crash_count = 0
    
    while True:
        log("启动 AI 伴侣核心进程 (main.py)...")
        # 启动主进程
        process = subprocess.Popen([sys.executable, "main.py"])
        
        try:
            process.wait()
        except KeyboardInterrupt:
            log("接收到停止信号，正在关闭系统...")
            process.terminate()
            break

        exit_code = process.returncode
        
        # 逻辑判断
        if exit_code == RESTART_EXIT_CODE:
            log("🔄 接收到 WebUI 热重启指令，正在重新拉起核心进程...")
            crash_count = 0  # 正常重启，清空错误计数
            time.sleep(1)
            continue
        elif exit_code == 0:
            log("核心进程已安全退出。")
            break
        else:
            crash_count += 1
            log(f"⚠️ 警告：AI 核心进程意外崩溃退出 (退出码: {exit_code}) (连续崩溃: {crash_count}/{MAX_CRASHES})")
            
            if crash_count >= MAX_CRASHES:
                log("🛑 致命：核心进程连续崩溃 3 次！守护进程放弃自动拉起。")
                log("🛠️ 正在启动 [应急救援 IDE 模式]...")
                
                # 拉起应急逃生舱进程
                em_process = subprocess.Popen([sys.executable, "emergency_webui.py"])
                try:
                    em_process.wait()
                except KeyboardInterrupt:
                    em_process.terminate()
                    break
                
                # 如果应急模式发出了热重启请求
                if em_process.returncode == RESTART_EXIT_CODE:
                    log("✅ 从应急模式收到了重启指令，尝试重新拉起主核心...")
                    crash_count = 0
                    continue
                else:
                    log("应急模式已退出，守护进程终止。")
                    break
            
            time.sleep(2) # 崩溃后等待 2 秒再重试，防止 CPU 爆满

if __name__ == "__main__":
    main()