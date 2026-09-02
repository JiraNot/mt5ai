# Security

## Overview

ระบบรักษาความปลอดภัยของข้อมูลและการเข้าถึง

## MT5 Credentials

```
เก็บใน .env หรือ Secret Manager
ห้ามลง Git

.env.example:
MT5_LOGIN=your_login
MT5_PASSWORD=your_password
MT5_SERVER=your_server
```

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
