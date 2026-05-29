"""
Garmin Connect 认证模块
- 邮箱+密码登录
- Token 持久化与自动恢复（garminconnect 0.3.3+ tokenstore API）
- MFA 双因素验证支持
- 中国区账号适配
- 代理环境兼容
"""

import os
import random
import re
import logging
import time
from pathlib import Path
from typing import Optional, Any
from types import MethodType

from garminconnect import Garmin, GarminConnectAuthenticationError
from garminconnect.client import (
    HAS_CFFI,
    WIDGET_DELAY_MAX_S,
    WIDGET_DELAY_MIN_S,
    _CSRF_RE,
    _MFARequired,
    _TITLE_RE,
    cffi_requests,
)
from garminconnect.exceptions import (
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)
from config_loader import get_garmin_config
from cn_client import GarminCnClient

logger = logging.getLogger(__name__)


class GarminAuth:
    """Garmin Connect 认证管理器"""

    DEFAULT_TOKEN_DIR = Path.home() / ".garminconnect"

    def __init__(
        self,
        email: Optional[str] = None,
        password: Optional[str] = None,
        is_cn: Optional[bool] = None,
        token_dir: Optional[str] = None,
        mfa_mode: Optional[str] = None,
    ):
        cfg = get_garmin_config()
        cfg_is_cn = cfg.get("is_cn", False)
        self.email = email or os.getenv("GARMIN_EMAIL", "")
        self.password = password or os.getenv("GARMIN_PASSWORD", "")
        self.email = self.email or cfg.get("email", "")
        self.password = self.password or cfg.get("password", "")
        self.is_cn = cfg_is_cn if is_cn is None else is_cn
        if token_dir:
            default_token_dir = token_dir
        elif os.getenv("GARMIN_TOKEN_DIR"):
            default_token_dir = os.getenv("GARMIN_TOKEN_DIR")
        elif is_cn is None or self.is_cn == cfg_is_cn:
            default_token_dir = cfg.get("token_dir") or self.DEFAULT_TOKEN_DIR
        else:
            default_token_dir = "~/.garminconnect-cn" if self.is_cn else "~/.garminconnect"
        self.token_dir = Path(default_token_dir).expanduser()
        self.mfa_mode = mfa_mode or cfg.get("mfa_mode", "prompt")
        self.client: Optional[Any] = None

    def _patch_cn_widget_login(self, client: Garmin) -> None:
        """Patch garminconnect CN widget login to consume tickets on connect.garmin.cn.

        Upstream currently requests widget tickets for sso.garmin.cn/sso/embed.
        That produces SSO cookies only; it does not set JWT_WEB for
        connectapi.garmin.cn.  For CN accounts, request tickets for
        https://connect.garmin.cn/app and consume them there.
        """
        if not self.is_cn or getattr(client.client, "_garmin_cn_widget_patch", False):
            return

        def cn_widget_web_login(inner, email: str, password: str) -> None:
            if not HAS_CFFI:
                raise GarminConnectConnectionError("curl_cffi not available")

            sess = cffi_requests.Session(impersonate="chrome", timeout=30)
            sso_base = f"{inner._sso}/sso"
            sso_embed = f"{sso_base}/embed"
            service_url = inner._portal_service_url
            embed_params = {
                "id": "gauth-widget",
                "embedWidget": "true",
                "gauthHost": sso_base,
            }
            signin_params = {
                **embed_params,
                "gauthHost": sso_embed,
                "service": service_url,
                "source": service_url,
                "redirectAfterAccountLoginUrl": service_url,
                "redirectAfterAccountCreationUrl": service_url,
            }

            response = sess.get(sso_embed, params=embed_params)
            if response.status_code == 429:
                raise GarminConnectTooManyRequestsError("Widget embed GET returned 429")
            if not response.ok:
                raise GarminConnectConnectionError(f"Widget embed returned {response.status_code}")

            response = sess.get(
                f"{sso_base}/signin",
                params=signin_params,
                headers={"Referer": sso_embed},
            )
            if response.status_code == 429:
                raise GarminConnectTooManyRequestsError("Widget signin GET returned 429")

            csrf_match = _CSRF_RE.search(response.text)
            if not csrf_match:
                raise GarminConnectConnectionError("Widget login: missing CSRF token")

            time.sleep(random.uniform(WIDGET_DELAY_MIN_S, WIDGET_DELAY_MAX_S))
            response = sess.post(
                f"{sso_base}/signin",
                params=signin_params,
                headers={"Referer": response.url},
                data={
                    "username": email,
                    "password": password,
                    "embed": "true",
                    "_csrf": csrf_match.group(1),
                },
                timeout=30,
            )
            if response.status_code == 429:
                raise GarminConnectTooManyRequestsError("Widget signin POST returned 429")

            title_match = _TITLE_RE.search(response.text)
            title = title_match.group(1) if title_match else ""
            title_lower = title.lower()
            if any(hint in title_lower for hint in ("bad gateway", "service unavailable", "cloudflare", "502", "503")):
                raise GarminConnectConnectionError(f"Widget login: server error '{title}'")
            if any(hint in title_lower for hint in ("locked", "invalid", "incorrect", "account error")):
                raise GarminConnectAuthenticationError(f"Widget authentication failed: '{title}'")
            if "MFA" in title:
                inner._mfa_session = sess
                inner._mfa_login_params = signin_params
                inner._mfa_post_headers = {"Referer": response.url}
                inner._mfa_flow = "widget"
                inner._widget_last_resp = response
                raise _MFARequired()
            if title != "Success":
                raise GarminConnectConnectionError(f"Widget login: unexpected title '{title}'")

            ticket_match = re.search(r"ticket=([^\"&]+)", response.text)
            if not ticket_match:
                raise GarminConnectConnectionError("Widget login: missing service ticket")

            inner._establish_session(ticket_match.group(1), sess=sess, service_url=service_url)

        client.client._widget_web_login = MethodType(cn_widget_web_login, client.client)
        client.client._garmin_cn_widget_patch = True

    @property
    def token_path(self) -> str:
        """返回 tokenstore 路径字符串（garminconnect 0.3.3+ 要求）"""
        return str(self.token_dir)

    def _prompt_mfa(self) -> str:
        """MFA 验证码输入"""
        if self.mfa_mode == "env":
            code = os.getenv("GARMIN_MFA_CODE", "")
            if code:
                return code
        return input("请输入 Garmin MFA 验证码: ")

    def _login_with_web_cookie(self) -> Optional[Garmin]:
        """Use a browser JWT_WEB cookie when password login cannot establish CN API auth."""
        jwt_web = os.getenv("GARMIN_JWT_WEB", "").strip()
        if not jwt_web:
            return None

        client = Garmin(is_cn=self.is_cn)
        client.client.jwt_web = jwt_web
        csrf = os.getenv("GARMIN_CSRF_TOKEN", "").strip()
        if csrf:
            client.client.csrf_token = csrf

        # Validate against the same API path normal login validates.
        client.get_user_profile()
        self.client = client
        logger.info("使用 GARMIN_JWT_WEB 登录成功 (%s)", "garmin.cn" if self.is_cn else "garmin.com")
        return self.client

    def login(self) -> Any:
        """
        登录 Garmin Connect
        - 优先使用已保存的 tokenstore 恢复会话
        - 失败则使用邮箱+密码登录
        - 使用 garminconnect 0.3.3+ 的 tokenstore API 自动持久化
        """
        # 1. 尝试使用已保存的 tokenstore 恢复会话
        logger.info(
            "Garmin login start: domain=%s token_dir=%s",
            "garmin.cn" if self.is_cn else "garmin.com",
            self.token_dir,
        )

        if self.is_cn:
            try:
                jwt_web = os.getenv("GARMIN_JWT_WEB", "").strip()
                csrf = os.getenv("GARMIN_CSRF_TOKEN", "").strip()
                cookie_header = os.getenv("GARMIN_COOKIE_HEADER", "").strip()
                client = GarminCnClient(
                    self.email,
                    self.password,
                    jwt_web=jwt_web,
                    csrf_token=csrf,
                    cookie_header=cookie_header,
                )
                client.login(tokenstore=self.token_path)
                self.client = client
                logger.info("CN login success")
                return self.client
            except Exception as e:
                logger.error("CN login failed: %s", e)
                raise GarminConnectAuthenticationError(
                    f"{e}. connect.garmin.cn 当前登录需要可用 JWT_WEB cookie 或浏览器会话。"
                ) from e

        try:
            cookie_client = self._login_with_web_cookie()
            if cookie_client is not None:
                return cookie_client
        except Exception as e:
            logger.warning("GARMIN_JWT_WEB 无效 (%s): %s", "garmin.cn" if self.is_cn else "garmin.com", e)

        if self.token_dir.exists() and any(self.token_dir.iterdir()):
            try:
                client = Garmin(is_cn=self.is_cn)
                self._patch_cn_widget_login(client)
                client.login(tokenstore=self.token_path)
                # 验证 token 是否有效
                client.get_user_profile()
                self.client = client
                logger.info("使用已保存的 Token 登录成功")
                return self.client
            except Exception as e:
                logger.warning("已保存的 Token 无效，将重新登录: %s", e)

        # 2. 使用邮箱+密码登录
        if not self.email or not self.password:
            raise GarminConnectAuthenticationError(
                "缺少登录凭据，请设置 GARMIN_EMAIL 和 GARMIN_PASSWORD 环境变量"
            )

        try:
            client = Garmin(
                email=self.email,
                password=self.password,
                is_cn=self.is_cn,
            )
            self._patch_cn_widget_login(client)
            mfa_status, _legacy_token = client.login(tokenstore=self.token_path)

            # MFA 处理
            if mfa_status == "mfa_code_required":
                logger.info("检测到 MFA 验证需求")
                mfa_code = self._prompt_mfa()
                if mfa_code:
                    mfa_status, _ = client.resume_login(mfa_code)

            self.client = client
            logger.info("邮箱密码登录成功 (%s)", "garmin.cn" if self.is_cn else "garmin.com")
            return self.client

        except Exception as e:
            domain = "garmin.cn" if self.is_cn else "garmin.com"
            logger.error("登录失败 (%s): %s", domain, e)
            if self.is_cn and not os.getenv("GARMIN_JWT_WEB"):
                raise GarminConnectAuthenticationError(
                    f"{e}. connect.garmin.cn 网页可登录但私有 API 登录失败时，"
                    "请从浏览器 Cookie 设置 GARMIN_JWT_WEB 后重试。"
                ) from e
            raise

    def diagnostic_snapshot(self) -> dict:
        """Read-only account snapshot for checking region/account correctness."""
        client = self.ensure_connected()
        profile = client.get_user_profile()
        devices = client.get_devices() or []
        activities = client.get_activities(0, 10) or []
        return {
            "domain": "garmin.cn" if self.is_cn else "garmin.com",
            "token_dir": str(self.token_dir),
            "profile": {
                "displayName": profile.get("displayName"),
                "profileId": profile.get("profileId") or profile.get("id"),
            },
            "devices": [
                {
                    "productDisplayName": d.get("productDisplayName"),
                    "deviceTypeSimpleName": d.get("deviceTypeSimpleName"),
                    "deviceStatus": d.get("deviceStatus"),
                    "deviceId": d.get("deviceId") or d.get("id"),
                }
                for d in devices
            ],
            "latest_activity": (
                {
                    "activityName": activities[0].get("activityName"),
                    "startTimeLocal": activities[0].get("startTimeLocal"),
                    "deviceId": activities[0].get("deviceId"),
                }
                if activities
                else None
            ),
            "recent_activity_count": len(activities),
        }

    def ensure_connected(self) -> Any:
        """确保连接有效，无效则重新登录"""
        if self.client is None:
            return self.login()

        try:
            self.client.get_user_profile()
            return self.client
        except Exception:
            logger.info("连接已失效，重新登录...")
            return self.login()

    def refresh_token(self) -> None:
        """手动刷新 token（通过重新访问 profile 触发自动刷新）"""
        if self.client is None:
            self.login()
            return

        try:
            self.client.get_user_profile()
            logger.info("Token 刷新成功")
        except Exception as e:
            logger.error("Token 刷新失败: %s", e)
            self.login()

    def logout(self) -> None:
        """登出"""
        if self.client:
            try:
                self.client.logout()
            except Exception:
                pass
            self.client = None
            logger.info("已登出")


# 单例便捷访问
_auth_instance: Optional[GarminAuth] = None


def get_auth() -> GarminAuth:
    """获取全局认证实例"""
    global _auth_instance
    if _auth_instance is None:
        _auth_instance = GarminAuth()
    return _auth_instance


def get_client() -> Any:
    """获取已认证的 Garmin 客户端"""
    auth = get_auth()
    return auth.ensure_connected()
