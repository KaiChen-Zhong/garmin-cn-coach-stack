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

## Full Cookie Header Fallback

If diagnosis still shows:

```text
CN app csrf missing
```

copy the full browser cookie header.

1. Keep Garmin Connect CN open in browser
2. Press `F12`
3. Open `Network`
4. Refresh `https://connect.garmin.cn/app/home`
5. Click request named `home` or `app`
6. Open `Headers`
7. Find `Request Headers`
8. Copy the whole `Cookie:` value
9. Put it into `.env`

```text
GARMIN_COOKIE_HEADER=paste_full_cookie_header_here
```

Keep `GARMIN_JWT_WEB` too if already filled.

## Retry

```powershell
.\.venv\Scripts\python.exe main.py diagnose --cn
```

## Security

- Never commit `.env`
- Never paste `JWT_WEB` into chat
- If leaked, log out Garmin web sessions and log in again to rotate cookie
