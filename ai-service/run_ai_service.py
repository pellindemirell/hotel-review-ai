import os
import sys
import subprocess
from pathlib import Path

# Windows CMD Unicode Ayarı
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# AI Servisi Dizin Bilgisi
BASE_DIR = Path(__file__).resolve().parent
VENV_DIR = BASE_DIR / ".venv"
REQUIREMENTS_FILE = BASE_DIR / "requirements.txt"

# OS Tabanlı Sanal Ortam Python ve Pip Yolları
if sys.platform == "win32":
    VENV_PYTHON = VENV_DIR / "Scripts" / "python.exe"
    VENV_UVICORN = VENV_DIR / "Scripts" / "uvicorn.exe"
else:
    VENV_PYTHON = VENV_DIR / "bin" / "python"
    VENV_UVICORN = VENV_DIR / "bin" / "uvicorn"


def print_banner():
    print("=" * 65)
    print(" >>> Python AI Servisi Otomatik Baslatici & Bagimlilik Yonetimi <<<")
    print("=" * 65)


def check_python_version():
    """Python sürüm kontrolü (Min 3.9)"""
    version = sys.version_info
    print(f"[+] Sistem Python Surumu: {version.major}.{version.minor}.{version.micro}")
    if version.major < 3 or (version.major == 3 and version.minor < 9):
        print("[!] HATA: Python 3.9 veya uzeri bir surum gereklidir!")
        sys.exit(1)


def ensure_virtualenv():
    """Sanal ortam (.venv) yoksa otomatik oluşturur"""
    if not VENV_DIR.exists() or not VENV_PYTHON.exists():
        print("[*] Sanal ortam (.venv) bulunamadi. Otomatik olusturuluyor...")
        try:
            subprocess.run([sys.executable, "-m", "venv", str(VENV_DIR)], check=True)
            print("[+] Sanal ortam (.venv) basariyla olusturuldu.")
        except Exception as e:
            print(f"[!] Sanal ortam olusturulamadi: {e}")
            sys.exit(1)
    else:
        print("[+] Sanal ortam (.venv) mevcut.")


def install_requirements():
    """Bağımlılıkları kontrol eder ve eksikse otomatik kurar"""
    if not REQUIREMENTS_FILE.exists():
        print("[!] requirements.txt bulunamadi, paket kontrolu atlaniyor.")
        return

    print("[*] Bagimliliklar (requirements.txt) kontrol ediliyor...")
    try:
        subprocess.run([str(VENV_PYTHON), "-m", "pip", "install", "--upgrade", "pip", "--quiet"], check=False)
        subprocess.run([str(VENV_PYTHON), "-m", "pip", "install", "-r", str(REQUIREMENTS_FILE)], check=True)
        print("[+] Tum Python paketleri guncel ve hazir.")
    except Exception as e:
        print(f"[!] Paketler yuklenirken bir uyari olustu: {e}")


def run_ai_service():
    """Uvicorn FastAPI sunucusunu port 8000 üzerinde çalıştırır"""
    print("\n[+] Python AI Servisi Baslatiliyor (http://localhost:8000)...")
    print("[i] Cikmak icin CTRL+C tuslarina basin.\n")

    os.chdir(str(BASE_DIR))
    
    env = os.environ.copy()
    env["PYTHONPATH"] = str(BASE_DIR)

    cmd = [
        str(VENV_PYTHON),
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        "0.0.0.0",
        "--port",
        "8000",
        "--reload"
    ]

    try:
        subprocess.run(cmd, env=env)
    except KeyboardInterrupt:
        print("\n[*] Python AI Servisi durduruldu.")


if __name__ == "__main__":
    print_banner()
    check_python_version()
    ensure_virtualenv()
    install_requirements()
    run_ai_service()
