# main.py
import asyncio
import uvicorn
import traceback
from web.api import app as fastapi_app
from bot.qq_client import start_bot
from core.logger import init_logger, logger
from tasks.proactive_manager import proactive_manager

async def run_web():
    config = uvicorn.Config(fastapi_app, host="0.0.0.0", port=5001, log_level="warning")
    server = uvicorn.Server(config)
    logger.info("🌐 WebUI 异步服务已启动 (端口: 5001)")
    await server.serve()

async def safe_task_runner(coro_func, task_name, *args, **kwargs):
    """
    安全任务装甲：包裹独立模块，防止单一协程抛出未捕获异常导致 asyncio.gather 崩溃。
    注意：传入的是协程函数(coro_func)本身，而不是协程实例，以便崩溃后能重新创建并执行。
    """
    while True:
        try:
            logger.info(f"⚙️ 挂载并启动系统模块: [{task_name}]")
            # 动态生成并执行协程
            await coro_func(*args, **kwargs)
            
            # 如果任务正常结束（例如未来有些非死循环的临时任务），则退出守护机制
            logger.info(f"✅ 模块 [{task_name}] 正常执行完毕退出。")
            break
            
        except asyncio.CancelledError:
            logger.info(f"🛑 模块 [{task_name}] 收到系统级取消信号，安全退出。")
            break
            
        except Exception as e:
            # 打印完整的堆栈报错信息，方便在日志中溯源是哪行代码引发的崩溃
            err_detail = traceback.format_exc()
            logger.error(f"❌ 致命异常拦截！模块 [{task_name}] 发生崩溃，已被安全装甲隔离防雪崩！\n异常信息: {e}\n{err_detail}")
            logger.info(f"🔄 正在尝试恢复，模块 [{task_name}] 将在 5 秒后执行热重启...")
            await asyncio.sleep(5)

async def main():
    init_logger()
    logger.info("🚀 正在启动 AI 伴侣单进程异步核心...")
    
    from core.config import cfg
    await cfg.load()
    
    # 将所有的核心与后台任务套上“安全装甲”后，挂载到并发池中
    # 任何一个模块死掉，都不会影响其他正在运行的模块
    await asyncio.gather(
        safe_task_runner(run_web, "WebUI 控制台"),
        safe_task_runner(start_bot, "NapCatQQ 通信监听"),
        safe_task_runner(proactive_manager.proactive_background_task, "主动搭话引擎"),
        safe_task_runner(proactive_manager.daily_weather_task, "每日天气与早安作息引擎")
    )

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 接收到退出信号，系统安全关闭。")