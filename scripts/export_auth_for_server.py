"""Helper script: Export Auth Login credentials from local machine to Server/Coolify.

รันสคริปต์นี้บนเครื่องของคุณ (PC/WSL) เพื่อ export ข้อมูล session ล็อกอิน
ไปใส่ใน Coolify Environment Variables บน Server โดยตรง ไม่ต้องใช้ API Key ใดๆ!
"""
import json
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

def main():
    print("=" * 60)
    print("Export Auth Login for Server (Coolify)")
    print("=" * 60)

    # 1. Codex / ChatGPT Auth
    codex_paths = [
        "/mnt/c/Users/Dulla/.codex/auth.json",
        r"C:\Users\Dulla\.codex\auth.json",
        os.path.expanduser("~/.codex/auth.json"),
    ]
    codex_data = None
    for cp in codex_paths:
        if os.path.exists(cp):
            try:
                with open(cp, "r", encoding="utf-8") as f:
                    codex_data = json.load(f)
                print(f"\n[OK] 1. Found ChatGPT/Codex Auth Session: {cp}")
                break
            except Exception as e:
                print(f"Read error {cp}: {e}")

    if codex_data:
        compact_codex = json.dumps(codex_data)
        print("\nCopy this value to Coolify (mt5ai -> Environment Variables):")
        print("-" * 60)
        print(f"CODEX_AUTH_JSON='{compact_codex}'")
        print("-" * 60)
    else:
        print("\n[!] ~/.codex/auth.json not found on this machine")

    # 2. Google ADC Auth
    appdata = os.environ.get("APPDATA", "")
    adc_paths = [
        os.path.expanduser("~/.config/gcloud/application_default_credentials.json"),
        "/home/dulla/.config/gcloud/application_default_credentials.json",
        os.path.join(appdata, "gcloud", "application_default_credentials.json") if appdata else "",
    ]
    adc_data = None
    for ap in adc_paths:
        if ap and os.path.exists(ap):
            try:
                with open(ap, "r", encoding="utf-8") as f:
                    adc_data = json.load(f)
                print(f"\n[OK] 2. Found Google ADC Auth Session: {ap}")
                break
            except Exception as e:
                print(f"Read error {ap}: {e}")

    if adc_data:
        compact_adc = json.dumps(adc_data)
        print("\nCopy this value to Coolify (mt5ai -> Environment Variables):")
        print("-" * 60)
        print(f"GOOGLE_ADC_JSON='{compact_adc}'")
        print("-" * 60)
    else:
        print("\n[i] 2. Google ADC (Gemini): Not yet generated on this machine")
        print("  To generate (run once):")
        print("  gcloud auth application-default login")
        print("  Then re-run this script to get GOOGLE_ADC_JSON")

    print("\n" + "=" * 60)
    print("Done! Once pasted in Coolify, click Redeploy.")
    print("=" * 60)

if __name__ == "__main__":
    main()
