#!/usr/bin/env python3
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

def run_server():
    """AI 서버를 실행하고 .env.local 변경을 감시하여 재시작합니다."""
    # ai-server 디렉토리로 이동
    server_dir = Path(__file__).parent / "apps" / "ai-server"
    env_file = server_dir / ".env.local"
    
    if not server_dir.exists():
        print(f"Error: {server_dir}를 찾을 수 없습니다.")
        return

    print("====================================================")
    print("🚀 AI Server 가중치 테스트 매니저 가동")
    print(f"📝 감시 파일: {env_file}")
    print("💡 .env.local을 수정하고 저장하면 서버가 자동 재시작됩니다.")
    print("⌨️  종료하려면 Ctrl+C를 누르세요.")
    print("====================================================")

    process = None
    last_mtime = env_file.stat().st_mtime if env_file.exists() else 0

    try:
        while True:
            # 서버 실행 (또는 재실행)
            if process is None:
                print("\n[INFO] AI 서버 시작 중...")
                process = subprocess.Popen(
                    [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"],
                    cwd=server_dir,
                    env={**os.environ, "PYTHONPATH": str(server_dir)}
                )

            # 파일 변경 감시 (1초 간격)
            time.sleep(1)
            
            if env_file.exists():
                current_mtime = env_file.stat().st_mtime
                if current_mtime > last_mtime:
                    print("\n[RESTART] .env.local 변경 감지! 서버를 재시작합니다...")
                    last_mtime = current_mtime
                    
                    # 기존 프로세스 종료
                    process.terminate()
                    process.wait()
                    process = None
            
            # 프로세스가 비정상 종료되었는지 확인
            if process and process.poll() is not None:
                print("\n[ERROR] 서버 프로세스가 종료되었습니다. 3초 후 재시도합니다.")
                process = None
                time.sleep(3)

    except KeyboardInterrupt:
        print("\n[STOP] 매니저를 종료합니다.")
        if process:
            process.terminate()
            process.wait()
        sys.exit(0)

if __name__ == "__main__":
    run_server()
