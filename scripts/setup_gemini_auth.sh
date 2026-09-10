#!/bin/bash
# ตั้งค่า Gemini ADC (Application Default Credentials)
# รันสคริปต์นี้ครั้งเดียวบน server

echo "=== ติดตั้ง gcloud CLI ==="
if ! command -v gcloud &> /dev/null; then
    curl -s https://dl.google.com/dl/cloudsdk/channels/rapid/downloads/google-cloud-cli-linux-x86_64.tar.gz -o /tmp/gcloud.tar.gz
    cd /tmp && tar xf gcloud.tar.gz
    /tmp/google-cloud-sdk/install.sh --quiet --path-update=true
    source ~/.bashrc
fi

echo "=== Login Google Account ==="
gcloud auth application-default login

echo "=== ตรวจสอบ credentials ==="
ls -la ~/.config/gcloud/application_default_credentials.json && echo "ADC: OK" || echo "ADC: FAIL"

echo ""
echo "=== ขั้นตอนต่อไป ==="
echo "Mount credentials เข้า Docker:"
echo "  volumes:"
echo "    - ~/.config/gcloud:/root/.config/gcloud:ro"
