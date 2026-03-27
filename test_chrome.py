import os
import platform
import time
from DrissionPage import ChromiumPage, ChromiumOptions

def test_chrome():
    print(f"Platform: {platform.system()}")
    print("Initializing ChromiumOptions...")
    options = ChromiumOptions()
    
    # 基本参数
    options.set_paths(browser_path='/usr/bin/google-chrome-stable')
    
    # 注入必备的容器参数
    options.set_argument("--no-sandbox")
    options.set_argument("--disable-dev-shm-usage")
    options.set_argument("--disable-gpu")
    
    # 设置为非无头模式（Silent 模式）
    print("Setting up non-headless (silent) options...")
    options.set_argument("--start-minimized")
    
    # 强制开启日志
    options.set_argument("--enable-logging")
    options.set_argument("--v=1")
    
    print("Starting ChromiumPage...")
    try:
        page = ChromiumPage(options)
        print("ChromiumPage started successfully!")
        
        print("Navigating to google.com...")
        page.get("https://www.google.com")
        
        print(f"Page title: {page.title}")
        print("Test passed! Browser is fully functional.")
        page.quit()
    except Exception as e:
        print(f"Failed to start ChromiumPage: {e}")

if __name__ == "__main__":
    test_chrome()
