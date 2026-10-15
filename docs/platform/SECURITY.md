# Security

## Overview

ระบบรักษาความปลอดภัยของข้อมูลและการเข้าถึง

## Binance API Credentials

```
เก็บใน Secret Manager หรือ Dashboard settings ที่เข้ารหัส
ห้ามลง Git

.env.example:
BINANCE_API_KEY=
BINANCE_API_SECRET=
```

ใช้สิทธิ์ API ขั้นต่ำที่จำเป็น และปิดการถอนเงินบน API key เสมอ

## API Authentication

```python
# JWT token required for all endpoints
# API key for programmatic access

# Token expiry: 24 hours
# Refresh token: 7 days
```

## Dashboard Security

```
- Login required
- Session timeout: 30 minutes
- No order execution without authorization
- Rate limiting on all endpoints
```

## Data Protection

```
- Passwords: hashed (bcrypt)
- API keys: hashed (SHA-256)
- Sensitive config: encrypted at rest
- Audit trail for all changes
```

## Network Security

```
- HTTPS in production
- CORS restricted to allowed origins
- Rate limiting per IP
- IP whitelisting (optional)
```

## Acceptance Criteria

- [ ] Credentials not in Git
- [ ] API authentication working
- [ ] Session management working
- [ ] Audit trail complete
