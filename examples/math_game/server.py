#!/usr/bin/env python3
"""
简单的 HTTP 服务器，用于运行数学游戏
解决浏览器 CORS 限制问题
"""

import http.server
import socketserver
import os
import webbrowser
from pathlib import Path


PORT = 8080


class MathGameHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    """自定义请求处理器，添加适当的 CORS 头"""
    
    def end_headers(self):
        # 添加 CORS 头
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        super().end_headers()
    
    def do_OPTIONS(self):
        """处理 OPTIONS 请求"""
        self.send_response(200)
        self.end_headers()


def main():
    # 切换到脚本所在目录
    script_dir = Path(__file__).parent
    os.chdir(script_dir)
    
    print("=" * 50)
    print("  小学数学竞赛游戏 - HTTP 服务器")
    print("=" * 50)
    print()
    
    # 检查必需文件是否存在
    required_files = ["index.html", "math_problems.json"]
    for filename in required_files:
        if not (script_dir / filename).exists():
            print(f"错误：找不到必需文件 {filename}")
            return
    
    # 尝试启动服务器
    try:
        with socketserver.TCPServer(("", PORT), MathGameHTTPRequestHandler) as httpd:
            server_url = f"http://localhost:{PORT}"
            
            print(f"服务器运行在: {server_url}")
            print(f"服务目录: {script_dir.absolute()}")
            print()
            print("按 Ctrl+C 停止服务器")
            print()
            
            # 尝试打开浏览器
            try:
                webbrowser.open(f"{server_url}/index.html")
                print("已自动打开浏览器...")
            except Exception as e:
                print(f"无法自动打开浏览器: {e}")
                print(f"请手动在浏览器中访问: {server_url}/index.html")
            
            print()
            print("-" * 50)
            
            # 启动服务器
            httpd.serve_forever()
            
    except OSError as e:
        if e.errno == 48:  # Address already in use
            print(f"端口 {PORT} 已被占用")
            print("请尝试:")
            print("1. 停止占用该端口的程序")
            print("2. 或者修改脚本中的 PORT 变量使用其他端口")
        else:
            print(f"启动服务器时出错: {e}")
    except KeyboardInterrupt:
        print()
        print("服务器已停止")


if __name__ == "__main__":
    main()
