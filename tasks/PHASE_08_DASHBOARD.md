# PHASE 08 — Dashboard

## Objective

สร้าง Dashboard สำหรับ monitor และ control ระบบ

## Tasks

### TASK 0801: API

- [ ] FastAPI setup
- [ ] Endpoint structure
- [ ] Error handling

**Acceptance:**
- API running

---

### TASK 0802: Authentication

- [ ] JWT authentication
- [ ] API key support
- [ ] Session management

**Acceptance:**
- Authentication working

---

### TASK 0803: Dashboard

- [ ] Streamlit prototype
- [x] Refresh live indicators without rerunning the whole dashboard
- [x] Dashboard-managed AI provider login/API settings
- [x] Real PTY browser login terminal for Codex, agy, and ClinePass
- [ ] Next.js production (planned)
- [x] ตรวจ Tablet ผ่าน Chromium จำลอง 5 ขนาด พร้อม HTTP/WebSocket จำลอง (2026-10-16)
- [x] เพิ่ม regression checks: web/tests/tablet-ux.cjs
- [x] แก้ Header/PANIC ถูกตัดบนจอกว้าง 768/820px — ย้ายเมนูเป็น 2 แถวบน Tablet Portrait และย่อเป็นไอคอนบนจอแคบ (2026-10-23)
- [ ] ขยายปุ่มสัมผัสที่ยังสูง 32–36px ให้ได้อย่างน้อย 44px
- [x] ยืนยัน Header UX หลังแก้ไขที่ 5 ขนาดจอ — ผลตรวจ: docs/testing/TABLET_UX_VERIFICATION.md (2026-10-23)
- [x] แสดง worker, execution mode และผล pipeline ล่าสุดพร้อมเวลาตัดสินใจบน Pro Desk (2026-10-23)
- [x] ให้ Settings API บันทึก entry score และ Volume/RSI toggles ที่ UI แสดง พร้อมผูกค่าเข้ากับ candidate triage และ strategy filters (2026-10-24)
- [x] ปรับ header ให้ใช้ความสูงตามเนื้อหาจนถึง 2xl เพื่อไม่ให้เมนู 2 แถวล้นแท็บเล็ตแนวนอน (2026-10-24)
- [ ] เพิ่มปุ่มทดสอบ Binance Futures Testnet API แบบอ่านข้อมูลบัญชีอย่างเดียว ไม่ส่งคำสั่งซื้อขาย (เพิ่มใน source 2026-10-24; รอตรวจหลัง deploy)

**Acceptance:**
- Dashboard accessible

---

### TASK 0804: Trades

- [ ] Trade journal view
- [ ] Filters
- [ ] Export

**Acceptance:**
- Trade journal working

---

### TASK 0805: Candidates

- [ ] Candidate feed
- [ ] Candidate detail
- [ ] Status tracking

**Acceptance:**
- Candidate view working

---

### TASK 0806: Strategy Analytics

- [ ] Strategy comparison
- [ ] Win rate charts
- [ ] P&L charts

**Acceptance:**
- Analytics working

---

### TASK 0807: Risk Monitor

- [ ] Risk status view
- [ ] Daily limits
- [ ] Drawdown

**Acceptance:**
- Risk monitor working

---

### TASK 0808: System Health

- [ ] Binance gateway status
- [ ] Database health
- [ ] Worker status

**Acceptance:**
- Health checks working

---

### TASK 0809: Emergency Controls

- [ ] Stop trading button
- [ ] Pause/Resume
- [ ] Close all positions

**Acceptance:**
- Emergency controls working

---

## Status

| Task | Status | Notes |
|------|--------|-------|
| 0801 | ⚠️ Not done | |
| 0802 | ⚠️ Not done | |
| 0803 | ✅ Done | Responsive Header และ live pipeline telemetry เพิ่มเติม 2026-10-23 |
| 0804 | ✅ Done | Streamlit |
| 0805 | ⚠️ Partial | |
| 0806 | ✅ Done | Basic |
| 0807 | ⚠️ Partial | |
| 0808 | ⚠️ Not done | |
| 0809 | ⚠️ Not done | |
