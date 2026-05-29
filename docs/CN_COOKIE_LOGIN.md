# Garmin CN Cookie Login

Garmin China sometimes blocks password API login even when browser login works.

When `python main.py diagnose --cn` shows:

```text
connect.garmin.cn 当前登录需要可用 JWT_WEB cookie 或浏览器会话
```

use browser cookie fallback.

## Steps

1. Open Chrome or Edge
2. Visit `https://connect.garmin.cn/app/home`
3. Log in with your own Garmin CN account
4. Confirm the Garmin dashboard loads normally
5. Press `F12`
6. Open `Application`
7. Open `Storage` -> `Cookies`
8. Select `https://connect.garmin.cn`
9. Find cookie named `JWT_WEB`
10. Copy its `Value`
11. Edit local `.env`

```text
GARMIN_JWT_WEB=paste_JWT_WEB_value_here
```

If write APIs fail later, also copy a CSRF token when available:

```text
GARMIN_CSRF_TOKEN=paste_csrf_value_here
```

For read-only diagnosis and export, `JWT_WEB` is usually enough.

## Retry

```powershell
.\.venv\Scripts\python.exe main.py diagnose --cn
```

## Security

- Never commit `.env`
- Never paste `JWT_WEB` into chat
- If leaked, log out Garmin web sessions and log in again to rotate cookie

