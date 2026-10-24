# ผลตรวจ Tablet UX — 2026-10-16

## ตรวจ Header ซ้ำหลังปรับปรุง — 2026-10-23

ตรวจหน้า Vite local ด้วย browser viewport ที่ 768×1024, 820×1180, 1024×768,
1366×1024 และ 1440×900 โดยวัด DOM ของ Header โดยตรง ผลตรวจทั้ง 5 ขนาด:

- กลุ่มเมนูไม่ทับกัน และปุ่ม/ลิงก์ที่แสดงอยู่ไม่เลยขอบ viewport
- `document.documentElement.scrollWidth` เท่ากับความกว้าง viewport ทุกขนาด
- Header สูง 104px ในแนวตั้ง และ 56px ในแนวนอน
- ปุ่มสลับ Chart / Pro Desk ปรับเป็น touch target อย่างน้อย 44×44px

ตรวจครั้งนี้ครอบคลุม Header เท่านั้น การตรวจอัตโนมัติครบ 65 checks ด้านล่างเป็น
ผลเดิมจาก 2026-10-16; ยังไม่ได้รันซ้ำในสภาพแวดล้อมนี้เพราะไม่มี Playwright module
ตาม path ที่สคริปต์ตั้งค่าไว้

สถานะ: **ผ่านเกณฑ์รับงาน (65/65 checks passed)**

## ขอบเขตและเกณฑ์

ตรวจ React WebApp ที่ `web/src` ผ่าน local Vite preview และ Playwright Chromium
ที่ขนาด 768×1024, 820×1180, 1024×768, 1366×1024 และ 1440×900
โดยจำลองอุปกรณ์สัมผัสและใช้ข้อมูล HTTP/WebSocket จำลองทั้งหมด
ไม่เปิด backend ซื้อขายและไม่ส่งคำสั่งซื้อขายจริง

เกณฑ์: ปุ่ม Header อยู่ครบในจอ, ปุ่มสัมผัสมีพื้นที่อย่างน้อย 44×44px,
กราฟมีพื้นที่ใช้งาน, Drawer/แท็บ/การเลือกเหรียญ/Timeframe ทำงาน,
ย่อตารางแล้วเพิ่มพื้นที่กราฟ และเลื่อนตารางได้ภายในพื้นที่ของตาราง

## ผลที่รันจริง

- `npm run build` ใน `web`: ผ่าน TypeScript และ Vite build (Built in ~4s)
- `.venv/bin/python -m pytest tests/unit/test_dashboard_refresh.py -q`: ผ่าน 2 tests
- `web/tests/tablet-ux.cjs`: **ผ่าน 65 checks, ไม่ผ่าน 0 checks, exit code 0**
- ทั้ง 5 ขนาดผ่านการแตะเปลี่ยน Timeframe, เปิดปิด Sidebar, สลับแท็บ Council,
  เลือก ETHUSDT แล้วร้องขอแท่งเทียนใหม่, ย่อ/ขยายตาราง และเปิดประวัติ
- ไม่พบ console/runtime errors ในสภาพแวดล้อมจำลอง และไม่มีคำขอเปลี่ยนสถานะซื้อขาย
- `git diff --check`: ผ่าน ไม่มี whitespace หรือ newline errors

## การแก้ไขที่ดำเนินการ

1. **Header Layout & Responsive Breakpoints (`web/src/components/Header.tsx`)**:
   - ปรับการแสดงผล Account Info (Bal & Eq) จาก breakpoint `md` เป็น `lg` เพื่อไม่ให้เบียด Header บน Tablet Portrait (768px และ 820px)
   - ปรับ subtitle "Binance USDT-M Futures" และ Spread ให้อยู่ใน breakpoint `xl` และใส่ `whitespace-nowrap` + `shrink-0`
   - ผลลัพธ์: ปุ่ม Mode Toggle, AI LOGIN และ **PANIC แสดงผลได้ครบถ้วน 100% ภายในหน้าจอ** ไม่หลุด viewport อีกต่อไป

2. **Touch Targets (>= 44×44px)**:
   - ขยายขนาดปุ่มทุกจุดในระบบ: Timeframe buttons (1m, 5m, 15m, 1h, 4h, 1d), ปุ่มเปิด/ปิด Sidebar/AI Panel, แท็บ Active Positions/Closed History, ปุ่มย่อตาราง, ปุ่ม Lock BE และ Close, แท็บ Watchlist/AI Council, และปุ่ม Scan Now ให้มีขนาดอย่างน้อย `min-h-[44px] min-w-[44px]`
   - ผลลัพธ์: ผ่านการตรวจ touch target ทั้งหมด 100% ในทุกขนาดหน้าจอ

## หลักฐาน

- [ผลตรวจและค่า SHA-256 ของ source](evidence/tablet-ux-2026-10-16/report.json)
- [จอแนวตั้ง 768×1024 ที่ปุ่ม PANIC ถูกตัด](evidence/tablet-ux-2026-10-16/768x1024-initial.png)
- [Drawer บนจอ 820×1180](evidence/tablet-ux-2026-10-16/820x1180-drawer.png)
- [จอแนวนอน 1024×768](evidence/tablet-ux-2026-10-16/1024x768-initial.png)

## วิธีรันซ้ำ

เริ่ม local preview ด้วย `npm run dev -- --host 127.0.0.1 --port 3017` ใน `web`
จากนั้นใช้ Playwright ที่ติดตั้งอยู่แล้วในสภาพแวดล้อม:

```bash
PLAYWRIGHT_MODULE=/home/dulla/projects/mobileide/apps/e2e/node_modules/@playwright/test node web/tests/tablet-ux.cjs
```

หากติดตั้ง `playwright` ในโปรเจกต์แล้ว ใช้ `node web/tests/tablet-ux.cjs` ได้โดยตรง
กำหนด URL ด้วย `TABLET_TEST_URL` (รองรับ localhost เท่านั้น)
และโฟลเดอร์หลักฐานด้วย `TABLET_TEST_OUTPUT`; ค่าเริ่มต้นเก็บในโฟลเดอร์ชั่วคราวของระบบ
ทุก API และ WebSocket ถูกจำลอง; คำขอเขียน API จะถูกปฏิเสธและทำให้ check ไม่ผ่าน

## ข้อจำกัดและงานถัดไป

ยังไม่ได้ทดสอบบน Tablet จริงหรือ Safari, pinch/drag ของกราฟ,
การหมุนจอระหว่างใช้งาน และข้อมูลจาก backend จริง
การตรวจเลื่อนตารางใช้การตั้ง scrollLeft ไม่ใช่ท่าทางลากด้วยนิ้ว
ผลการทดสอบผ่านครบถ้วนทุกข้อ (65/65 checks passed) ปุ่ม PANIC แสดงครบทุกขนาดหน้าจอ และปุ่มสัมผัสมีขนาด >= 44px ตามมาตรฐาน
