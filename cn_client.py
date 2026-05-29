"""
Garmin Connect CN direct client.

Uses browser-like SSO + gc-api paths from connect.garmin.cn/app.
This avoids garminconnect's global-only assumptions and returns the
latest CN data seen in the web UI.
"""

from __future__ import annotations

import json
import logging
import random
import re
import time
import base64
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import requests
from garminconnect.client import cffi_requests, _CSRF_RE, _TITLE_RE

logger = logging.getLogger(__name__)


@dataclass
class _CnProfile:
    display_name: str
    profile_id: int
    user_profile_pk: int
    full_name: str = ""
    username: str = ""
    raw: dict[str, Any] | None = None


class GarminCnClient:
    def __init__(
        self,
        email: str,
        password: str,
        jwt_web: str | None = None,
        csrf_token: str | None = None,
        cookie_header: str | None = None,
    ):
        self.email = email
        self.password = password
        self.jwt_web = jwt_web or ""
        self.csrf_override = csrf_token or ""
        self.cookie_header_override = cookie_header or ""
        self.session = cffi_requests.Session(impersonate="chrome", timeout=30)
        self.app_session = requests.Session()
        self.app_session.headers.update({"User-Agent": "Mozilla/5.0"})
        self.cookies_header = ""
        self.csrf_token = ""
        self.bearer_token = ""
        self.profile: _CnProfile | None = None
        self.preferences: dict[str, Any] = {}
        self._logged_in = False

    def login(self, tokenstore: str | None = None) -> "GarminCnClient":
        del tokenstore
        if self.jwt_web or self.cookie_header_override:
            self._login_via_cookie()
        else:
            self._login_via_widget()
        self._load_app_context()
        self._fetch_bearer_token()
        self._logged_in = True
        return self

    def ensure_connected(self) -> "GarminCnClient":
        if not self._logged_in:
            return self.login()
        try:
            self.get_current_user_info()
        except Exception:
            self._logged_in = False
            return self.login()
        return self

    def _login_via_cookie(self) -> None:
        if not self.jwt_web and not self.cookie_header_override:
            raise RuntimeError("CN cookie login requires JWT_WEB or GARMIN_COOKIE_HEADER")
        cookie_pairs: dict[str, str] = {}
        if self.cookie_header_override:
            for item in self.cookie_header_override.split(";"):
                if "=" not in item:
                    continue
                key, value = item.strip().split("=", 1)
                if key and value:
                    cookie_pairs[key] = value
        if self.jwt_web:
            cookie_pairs["JWT_WEB"] = self.jwt_web
        if "JWT_WEB" not in cookie_pairs:
            raise RuntimeError("CN cookie login requires JWT_WEB cookie")
        for domain in (".connect.garmin.cn", "connect.garmin.cn"):
            for key, value in cookie_pairs.items():
                self.session.cookies.set(key, value, domain=domain, path="/")
                self.app_session.cookies.set(key, value, domain=domain, path="/")
        if self.csrf_override:
            self.csrf_token = self.csrf_override
        self.cookies_header = "; ".join(f"{key}={value}" for key, value in cookie_pairs.items())

    def _login_via_widget(self) -> None:
        sso_base = "https://sso.garmin.cn/sso"
        sso_embed = f"{sso_base}/embed"
        service = "https://connect.garmin.cn/app"
        embed_params = {
            "id": "gauth-widget",
            "embedWidget": "true",
            "gauthHost": sso_base,
        }
        signin_params = {
            **embed_params,
            "gauthHost": sso_embed,
            "service": service,
            "source": service,
            "redirectAfterAccountLoginUrl": service,
            "redirectAfterAccountCreationUrl": service,
        }

        r = self.session.get(sso_embed, params=embed_params)
        if r.status_code == 429:
            raise RuntimeError("CN widget embed rate limited")
        r = self.session.get(f"{sso_base}/signin", params=signin_params, headers={"Referer": sso_embed})
        if r.status_code == 429:
            raise RuntimeError("CN widget signin rate limited")
        csrf = _CSRF_RE.search(r.text)
        if not csrf:
            raise RuntimeError("CN widget CSRF missing")

        time.sleep(random.uniform(3, 8))
        r = self.session.post(
            f"{sso_base}/signin",
            params=signin_params,
            headers={"Referer": r.url},
            data={
                "username": self.email,
                "password": self.password,
                "embed": "true",
                "_csrf": csrf.group(1),
            },
            timeout=30,
        )
        title = _TITLE_RE.search(r.text)
        if title and title.group(1) != "Success":
            raise RuntimeError(f"CN login failed: {title.group(1)}")

        ticket = re.search(r'ticket=([^"&#]+)', r.text)
        if not ticket:
            raise RuntimeError("CN login: missing service ticket")

        final = self.session.get(service, params={"ticket": ticket.group(1)}, allow_redirects=True, timeout=30)
        if final.status_code >= 400:
            raise RuntimeError(f"CN login: ticket consume failed {final.status_code}")

        jar = list(self.session.cookies.jar)
        self.cookies_header = "; ".join(f"{c.name}={c.value}" for c in jar if "garmin.cn" in c.domain)
        if not any(c.name == "JWT_WEB" for c in jar):
            raise RuntimeError("CN login: JWT_WEB missing")

    def _extract_window_json(self, html: str, variable: str) -> dict[str, Any] | None:
        marker = f"window.{variable}"
        idx = html.find(marker)
        if idx < 0:
            return None
        eq = html.find("=", idx)
        if eq < 0:
            return None
        start = html.find("{", eq)
        if start < 0:
            return None
        try:
            value, _end = json.JSONDecoder().raw_decode(html[start:])
        except json.JSONDecodeError:
            return None
        return value if isinstance(value, dict) else None

    def _load_app_context(self) -> None:
        r = self.app_session.get(
            "https://connect.garmin.cn/app",
            headers={"Cookie": self.cookies_header, "User-Agent": "Mozilla/5.0"},
            timeout=30,
        )
        if r.status_code != 200:
            raise RuntimeError(f"CN app load failed: {r.status_code}")

        csrf = re.search(r'<meta name="csrf-token" content="([^"]+)"', r.text)
        if csrf:
            self.csrf_token = csrf.group(1)
        elif self.csrf_override:
            self.csrf_token = self.csrf_override
        else:
            raise RuntimeError("CN app csrf missing")

        viewer_data = self._extract_window_json(r.text, "VIEWER_SOCIAL_PROFILE")
        if not viewer_data:
            raise RuntimeError("CN viewer profile missing")
        self.profile = _CnProfile(
            display_name=viewer_data["displayName"],
            profile_id=int(viewer_data["profileId"]),
            user_profile_pk=int(viewer_data["profileId"]),
            full_name=viewer_data.get("fullName", ""),
            username=viewer_data.get("userName", ""),
            raw=viewer_data,
        )

        pref = self._extract_window_json(r.text, "PREFERENCES")
        if pref:
            self.preferences = pref

        if not self.csrf_token and self.csrf_override:
            self.csrf_token = self.csrf_override

    def _fetch_bearer_token(self) -> None:
        headers = self._base_headers(include_auth=False)
        r = self.app_session.post(
            "https://connect.garmin.cn/web-api/services/auth/token/public",
            headers=headers,
            json={},
            timeout=30,
        )
        if r.status_code not in (200, 201):
            raise RuntimeError(f"CN token fetch failed: {r.status_code}")
        self.bearer_token = r.json()["access_token"]

    def _base_headers(self, include_auth: bool = True) -> dict[str, str]:
        headers = {
            "Accept": "application/json, text/plain, */*",
            "NK": "NT",
            "Origin": "https://connect.garmin.cn",
            "Referer": "https://connect.garmin.cn/app",
            "User-Agent": "Mozilla/5.0",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Cookie": self.cookies_header,
            "X-Requested-With": "XMLHttpRequest",
            "Connect-Csrf-Token": self.csrf_token,
            "DI-Backend": "connectapi.garmin.cn",
        }
        if include_auth and self.bearer_token:
            headers["Authorization"] = f"Bearer {self.bearer_token}"
        return headers

    def _display_name(self) -> str:
        if self.profile and self.profile.display_name:
            return self.profile.display_name
        raise RuntimeError("CN profile missing displayName")

    def _first_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        try:
            return self._api(path, params)
        except Exception:
            return None

    def _normalize_dict(self, value: Any, fallback: dict[str, Any] | None = None) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        return fallback or {}

    def _normalize_list(self, value: Any) -> list[dict[str, Any]]:
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            for key in ("data", "activities", "items", "results"):
                candidate = value.get(key)
                if isinstance(candidate, list):
                    return candidate
        return []

    def _api(self, path: str, params: dict[str, Any] | None = None) -> Any:
        r = self.app_session.get(
            f"https://connect.garmin.cn/gc-api{path}",
            headers=self._base_headers(),
            params=params,
            timeout=30,
        )
        if r.status_code >= 400:
            raise RuntimeError(f"CN API {path} failed: {r.status_code} {r.text[:120]}")
        return r.json()

    def _api_post(self, path: str, payload: Any = None) -> Any:
        r = self.app_session.post(
            f"https://connect.garmin.cn/gc-api{path}",
            headers=self._base_headers(),
            json=payload,
            timeout=30,
        )
        if r.status_code >= 400:
            raise RuntimeError(f"CN API POST {path} failed: {r.status_code} {r.text[:160]}")
        if r.status_code == 204:
            return {}
        return r.json() if r.text else {}

    def _api_put(self, path: str, payload: Any = None) -> Any:
        r = self.app_session.put(
            f"https://connect.garmin.cn/gc-api{path}",
            headers=self._base_headers(),
            json=payload,
            timeout=30,
        )
        if r.status_code >= 400:
            raise RuntimeError(f"CN API PUT {path} failed: {r.status_code} {r.text[:160]}")
        if r.status_code == 204:
            return {}
        return r.json() if r.text else {}

    def _api_delete(self, path: str) -> Any:
        r = self.app_session.delete(
            f"https://connect.garmin.cn/gc-api{path}",
            headers=self._base_headers(),
            timeout=30,
        )
        if r.status_code >= 400:
            raise RuntimeError(f"CN API DELETE {path} failed: {r.status_code} {r.text[:160]}")
        if r.status_code == 204:
            return {}
        return r.json() if r.text else {}

    def _raw_get(self, path: str, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> bytes:
        r = self.app_session.get(
            f"https://connect.garmin.cn/gc-api{path}",
            headers={**self._base_headers(), **(headers or {})},
            params=params,
            timeout=60,
        )
        if r.status_code >= 400:
            raise RuntimeError(f"CN raw GET {path} failed: {r.status_code} {r.text[:160]}")
        return r.content

    def _raw_post(self, path: str, payload: Any = None, headers: dict[str, str] | None = None, files: Any = None) -> Any:
        r = self.app_session.post(
            f"https://connect.garmin.cn/gc-api{path}",
            headers={**self._base_headers(), **(headers or {})},
            json=payload if files is None else None,
            files=files,
            timeout=60,
        )
        if r.status_code >= 400:
            raise RuntimeError(f"CN raw POST {path} failed: {r.status_code} {r.text[:160]}")
        return r.json() if r.text else {}

    def _raw_put(self, path: str, payload: Any = None, headers: dict[str, str] | None = None) -> Any:
        r = self.app_session.put(
            f"https://connect.garmin.cn/gc-api{path}",
            headers={**self._base_headers(), **(headers or {})},
            json=payload,
            timeout=60,
        )
        if r.status_code >= 400:
            raise RuntimeError(f"CN raw PUT {path} failed: {r.status_code} {r.text[:160]}")
        return r.json() if r.text else {}

    def _raw_delete(self, path: str, headers: dict[str, str] | None = None) -> Any:
        r = self.app_session.delete(
            f"https://connect.garmin.cn/gc-api{path}",
            headers={**self._base_headers(), **(headers or {})},
            timeout=60,
        )
        if r.status_code >= 400:
            raise RuntimeError(f"CN raw DELETE {path} failed: {r.status_code} {r.text[:160]}")
        return r.json() if r.text else {}

    def connectapi(self, path: str, params: dict[str, Any] | None = None) -> Any:
        return self._api(path, params)

    def download(self, path: str, **kwargs: Any) -> bytes:
        return self._raw_get(path, params=kwargs or None)

    def query_garmin_graphql(self, query: dict[str, Any]) -> dict[str, Any]:
        return self._raw_post("/graphql-gateway/graphql", query)

    def connectwebproxy(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("connectwebproxy not implemented for CN client")

    def logout(self) -> None:
        self._logged_in = False
        self.cookies_header = ""
        self.csrf_token = ""
        self.bearer_token = ""
        self.profile = None
        self.preferences = {}

    def __getattr__(self, name: str):
        dynamic = {
            "count_activities": lambda: self._count_activities(),
            "get_activities_by_date": lambda startdate, enddate=None, activitytype=None, sortorder=None: self._get_activities_by_date(startdate, enddate, activitytype, sortorder),
            "get_activities_fordate": lambda fordate: self._api(f"/mobile-gateway/heartRate/forDate/{fordate}"),
            "get_activity_hr_in_timezones": lambda activity_id: self._api(f"/activity-service/activity/{activity_id}/hrTimeInZones"),
            "get_activity_power_in_timezones": lambda activity_id: self._api(f"/activity-service/activity/{activity_id}/powerTimeInZones"),
            "get_activity_split_summaries": lambda activity_id: self._api(f"/activity-service/activity/{activity_id}/split_summaries"),
            "get_activity_splits": lambda activity_id: self._api(f"/activity-service/activity/{activity_id}/splits"),
            "get_activity_typed_splits": lambda activity_id: self._api(f"/activity-service/activity/{activity_id}/typed_splits"),
            "get_activity_exercise_sets": lambda activity_id: self._api(f"/activity-service/activity/{activity_id}/exerciseSets"),
            "get_activity_gear": lambda activity_id: self._api("/gear-service/gear/filterGear", {"activityId": str(activity_id)}),
            "get_activity_types": lambda: self._api("/activity-service/activity/activityTypes"),
            "get_all_day_events": lambda cdate: self._api("/wellness-service/wellness/dailyEvents", {"calendarDate": cdate}),
            "get_adaptive_training_plan_by_id": lambda plan_id: self._api(f"/trainingplan-service/trainingplan/fbt-adaptive/{plan_id}"),
            "get_blood_pressure": lambda startdate, enddate=None: self._api(f"/bloodpressure-service/bloodpressure/range/{startdate}/{enddate or startdate}", {"includeAll": True}),
            "delete_blood_pressure": lambda version, cdate: self._api_delete(f"/bloodpressure-service/bloodpressure/{cdate}/{version}"),
            "get_daily_weigh_ins": lambda cdate: self._api(f"/weight-service/weight/dayview/{cdate}", {"includeAll": True}),
            "delete_weigh_in": lambda weight_pk, cdate: self._api_delete(f"/weight-service/weight/{cdate}/byversion/{weight_pk}"),
            "delete_weigh_ins": lambda cdate, delete_all=False: self._delete_weigh_ins(cdate, delete_all),
            "get_device_last_used": lambda: self._api("/device-service/deviceservice/mylastused"),
            "get_device_solar_data": lambda device_id, startdate, enddate=None: self._get_device_solar_data(device_id, startdate, enddate),
            "get_full_name": lambda: self.profile.full_name if self.profile else "",
            "get_gear_activities": lambda gearUUID, limit=1000: self._api(f"/activitylist-service/activities/{gearUUID}/gear", {"start": 0, "limit": min(int(limit), 1000)}),
            "get_gear_stats": lambda gearUUID: self._api(f"/gear-service/gear/stats/{gearUUID}"),
            "get_golf_scorecard": lambda scorecard_id: self._api("/golf-service/scorecard/detail", {"scorecard-ids": str(scorecard_id), "include-longest-shot-distance": "true"}),
            "get_golf_shot_data": lambda scorecard_id, hole_numbers="1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18": self._api(f"/golf-service/shot/scorecard/{scorecard_id}/hole", {"hole-numbers": hole_numbers}),
            "get_inprogress_virtual_challenges": lambda start, limit: self._api("/badgechallenge-service/virtualChallenge/inProgress", {"start": str(start), "limit": str(limit)}),
            "get_menstrual_calendar_data": lambda startdate, enddate: self._api(f"/periodichealth-service/menstrualcycle/calendar/{startdate}/{enddate}"),
            "get_menstrual_data_for_date": lambda fordate: self._api(f"/periodichealth-service/menstrualcycle/dayview/{fordate}"),
            "get_nutrition_daily_settings": lambda cdate: self._api(f"/nutrition-service/settings/{cdate}"),
            "get_pregnancy_summary": lambda: self._api("/periodichealth-service/menstrualcycle/pregnancysnapshot"),
            "get_primary_training_device": lambda: self._api("/web-gateway/device-info/primary-training-device"),
            "get_scheduled_workout_by_id": lambda scheduled_workout_id: self._api(f"/workout-service/schedule/{scheduled_workout_id}"),
            "get_training_plan_by_id": lambda plan_id: self._api(f"/trainingplan-service/trainingplan/phased/{plan_id}"),
            "get_user_summary": lambda cdate: self._api(f"/usersummary-service/usersummary/daily/{self._display_name()}", {"calendarDate": cdate}),
            "get_workout_by_id": lambda workout_id: self._api(f"/workout-service/workout/{workout_id}"),
            "request_reload": lambda cdate: self._api_post(f"/wellness-service/wellness/epoch/request/{cdate}", {}),
            "set_activity_name": lambda activity_id, title: self._api_put(f"/activity-service/activity/{activity_id}", {"activityId": activity_id, "activityName": title}),
            "set_activity_type": lambda activity_id, type_id, type_key, parent_type_id: self._api_put(f"/activity-service/activity/{activity_id}", {"activityId": activity_id, "activityTypeDTO": {"typeId": type_id, "typeKey": type_key, "parentTypeId": parent_type_id}}),
            "set_gear_default": lambda activityType, gearUUID, defaultGear=True: self._set_gear_default(activityType, gearUUID, defaultGear),
            "download_workout": lambda workout_id: self._raw_get(f"/workout-service/workout/FIT/{workout_id}"),
            "delete_activity": lambda activity_id: self._api_delete(f"/activity-service/activity/{activity_id}"),
            "add_gear_to_activity": lambda gearUUID, activity_id: self._api_put(f"/gear-service/gear/link/{gearUUID}/activity/{activity_id}"),
            "remove_gear_from_activity": lambda gearUUID, activity_id: self._api_put(f"/gear-service/gear/unlink/{gearUUID}/activity/{activity_id}"),
            "create_manual_activity_from_json": lambda payload: self._api_post("/activity-service/activity", payload),
            "add_weigh_in_with_timestamps": lambda weight, unitKey="kg", dateTimestamp="", gmtTimestamp="": self._add_weigh_in_with_timestamps(weight, unitKey, dateTimestamp, gmtTimestamp),
            "delete_weigh_ins": lambda cdate, delete_all=False: self._delete_weigh_ins(cdate, delete_all),
        }
        if name in dynamic:
            return dynamic[name]
        raise AttributeError(name)

    def _count_activities(self) -> int:
        data = self._api("/activitylist-service/activities/count")
        if not isinstance(data, dict) or "totalCount" not in data:
            raise RuntimeError("No activities count data received")
        return int(data["totalCount"])

    def _get_activities_by_date(self, startdate: str, enddate: str | None = None, activitytype: str | None = None, sortorder: str | None = None) -> list[dict[str, Any]]:
        startdate = str(startdate)
        params: dict[str, Any] = {"startDate": startdate, "start": "0", "limit": "20"}
        if enddate:
            params["endDate"] = enddate
        if activitytype:
            params["activityType"] = activitytype
        if sortorder:
            params["sortOrder"] = sortorder
        out: list[dict[str, Any]] = []
        while True:
            page = self._api("/activitylist-service/activities", params)
            if page:
                if isinstance(page, list):
                    out.extend(x for x in page if isinstance(x, dict))
                elif isinstance(page, dict) and "activityList" in page and isinstance(page["activityList"], list):
                    out.extend(x for x in page["activityList"] if isinstance(x, dict))
                else:
                    break
                params["start"] = str(int(params["start"]) + int(params["limit"]))
            else:
                break
        return out

    def _get_device_solar_data(self, device_id: Any, startdate: str, enddate: str | None = None) -> list[dict[str, Any]]:
        single_day = enddate is None
        if enddate is None:
            enddate = startdate
        resp = self._api(f"/web-gateway/solar/{device_id}/{startdate}/{enddate}", {"singleDayView": single_day})
        if not resp or "deviceSolarInput" not in resp:
            raise RuntimeError("No device solar input data received")
        return resp["deviceSolarInput"]

    def _delete_weigh_ins(self, cdate: str, delete_all: bool = False) -> int | None:
        daily = self._api(f"/weight-service/weight/dayview/{cdate}", {"includeAll": True})
        weigh_ins = (daily or {}).get("dateWeightList", []) if isinstance(daily, dict) else []
        if not weigh_ins:
            return None
        if len(weigh_ins) > 1 and not delete_all:
            return None
        for w in weigh_ins:
            self._api_delete(f"/weight-service/weight/{cdate}/byversion/{w['samplePk']}")
        return len(weigh_ins)

    def _add_weigh_in_with_timestamps(self, weight: int | float, unitKey: str = "kg", dateTimestamp: str = "", gmtTimestamp: str = "") -> dict[str, Any]:
        if not dateTimestamp:
            dateTimestamp = datetime.now().astimezone().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]
        if not gmtTimestamp:
            gmtTimestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]
        payload = {
            "dateTimestamp": dateTimestamp,
            "gmtTimestamp": gmtTimestamp,
            "unitKey": unitKey,
            "sourceType": "MANUAL",
            "value": weight,
        }
        return self._api_post("/weight-service/user-weight", payload)

    def _set_gear_default(self, activityType: str, gearUUID: str, defaultGear: bool = True) -> Any:
        suffix = "/default/true" if defaultGear else ""
        method = "PUT" if defaultGear else "DELETE"
        path = f"/gear-service/gear/{gearUUID}/activityType/{activityType}{suffix}"
        if method == "PUT":
            return self._api_put(path)
        return self._api_delete(path)

    def get_user_profile(self) -> dict[str, Any]:
        info = self._first_json("/currentuser-service/user/info") or {}
        profile = self.profile.raw or {}
        if isinstance(info, dict):
            merged = {**profile, **info}
            merged.setdefault("displayName", self.profile.display_name if self.profile else "")
            merged.setdefault("profileId", self.profile.profile_id if self.profile else None)
            return merged
        return profile

    def get_userprofile_settings(self) -> dict[str, Any]:
        settings = self._first_json("/userprofile-service/userprofile/user-settings") or {}
        if isinstance(settings, dict):
            settings.setdefault("preferences", self.preferences)
            return settings
        return {"preferences": self.preferences}

    def get_current_user_info(self) -> dict[str, Any]:
        return self._api("/currentuser-service/user/info")

    def get_activities(self, start: int = 0, limit: int = 30) -> list[dict[str, Any]]:
        data = self._api("/activitylist-service/activities/search/activities", {"start": start, "limit": limit})
        return self._normalize_list(data)

    def get_activity(self, activity_id: str) -> dict[str, Any]:
        return self._api(f"/activity-service/activity/{activity_id}")

    def get_activity_details(self, activity_id: str) -> dict[str, Any]:
        return self._api(f"/activity-service/activity/{activity_id}/details")

    def get_activity_weather(self, activity_id: str) -> dict[str, Any]:
        return self._api(f"/activity-service/activity/{activity_id}/weather")

    def download_activity(self, activity_id: str, dl_fmt: Any = None) -> Any:
        fmt = str(dl_fmt).lower() if dl_fmt is not None else ""
        if fmt.endswith("gpx"):
            path = f"/download-service/export/gpx/activity/{activity_id}"
        elif fmt.endswith("tcx"):
            path = f"/download-service/export/tcx/activity/{activity_id}"
        else:
            path = f"/download-service/files/activity/{activity_id}"
        r = self.app_session.get(
            f"https://connect.garmin.cn/gc-api{path}",
            headers=self._base_headers(),
            timeout=30,
        )
        if r.status_code >= 400:
            raise RuntimeError(f"CN download failed: {r.status_code}")
        return r.content

    def get_devices(self) -> list[dict[str, Any]]:
        return self._normalize_list(self._api(f"/device-service/deviceservice/device-info/all/{self._display_name()}"))

    def get_device_settings(self, device_id: Any) -> dict[str, Any]:
        try:
            return self._api(f"/device-service/deviceservice/device-settings/{device_id}")
        except Exception:
            return {}

    def get_device_alarms(self) -> list[dict[str, Any]]:
        try:
            return self._normalize_list(self._api("/device-service/deviceservice/alarms"))
        except Exception:
            return []

    def get_floors(self, date_str: str) -> dict[str, Any]:
        return self._normalize_dict(self._first_json(f"/wellness-service/wellness/floorsChartData/daily/{date_str}") or self._first_json("/wellness-service/wellness/floorsChartData/daily", {"date": date_str}))

    def get_sleep_data(self, date_str: str) -> dict[str, Any]:
        return self._normalize_dict(
            self._first_json("/wellness-service/wellness/dailySleep", {"date": date_str})
            or self._first_json("/wellness-service/wellness/dailySleepData", {"date": date_str})
        )

    def get_heart_rates(self, date_str: str) -> dict[str, Any]:
        return self._normalize_dict(self._api(f"/wellness-service/wellness/dailyHeartRate/{self._display_name()}", {"date": date_str}))

    def get_steps_data(self, date_str: str) -> list[dict[str, Any]]:
        return self._normalize_list(self._api(f"/wellness-service/wellness/dailySummaryChart/{self._display_name()}", {"date": date_str}))

    def get_daily_steps(self, date_str: str) -> dict[str, Any]:
        steps = self.get_steps_data(date_str)
        total = sum(item.get("steps", 0) for item in steps if isinstance(item, dict))
        return {"date": date_str, "steps": total}

    def get_rhr_day(self, date_str: str) -> dict[str, Any]:
        hr = self.get_heart_rates(date_str)
        return {"calendarDate": date_str, "restingHeartRate": hr.get("restingHeartRate")}

    def get_stress_data(self, date_str: str) -> dict[str, Any]:
        return self._normalize_dict(
            self._first_json(f"/wellness-service/wellness/dailyStress/{self._display_name()}", {"date": date_str})
            or self._first_json("/wellness-service/wellness/dailyStress", {"date": date_str})
        )

    def get_all_day_stress(self, date_str: str) -> dict[str, Any]:
        return self.get_stress_data(date_str)

    def get_body_battery(self, date_str: str) -> list[dict[str, Any]]:
        try:
            data = self._first_json(f"/wellness-service/wellness/bodyBattery/{self._display_name()}", {"date": date_str})
            if data is None:
                data = self._first_json("/wellness-service/wellness/bodyBattery/reports/daily", {"startDate": date_str, "endDate": date_str})
            return self._normalize_list(data)
        except Exception:
            return []

    def get_body_battery_events(self, date_str: str) -> list[dict[str, Any]]:
        return []

    def get_respiration_data(self, date_str: str) -> dict[str, Any]:
        return self._normalize_dict(self._first_json(f"/wellness-service/wellness/daily/respiration/{date_str}") or self._first_json(f"/wellness-service/wellness/respiration/{self._display_name()}", {"date": date_str}))

    def get_spo2_data(self, date_str: str) -> dict[str, Any]:
        return self._normalize_dict(self._first_json(f"/wellness-service/wellness/daily/spo2/{date_str}") or self._first_json(f"/wellness-service/wellness/oxygenSaturation/{self._display_name()}", {"date": date_str}))

    def get_hrv_data(self, date_str: str) -> dict[str, Any]:
        try:
            return self._normalize_dict(self._api(f"/hrv-service/hrv/{date_str}"))
        except Exception:
            return {}

    def get_training_status(self, date_str: str) -> dict[str, Any]:
        try:
            return self._normalize_dict(self._first_json(f"/metrics-service/metrics/trainingstatus/aggregated/{date_str}") or self._api("/wellness-service/wellness/trainingStatus", {"date": date_str}))
        except Exception:
            return {}

    def get_training_readiness(self, date_str: str) -> dict[str, Any]:
        try:
            return self._normalize_dict(self._first_json(f"/metrics-service/metrics/trainingreadiness/{date_str}") or self._api("/wellness-service/wellness/trainingReadiness", {"date": date_str}))
        except Exception:
            return {}

    def get_morning_training_readiness(self, date_str: str) -> dict[str, Any]:
        return {}

    def get_intensity_minutes_data(self, date_str: str) -> dict[str, Any]:
        try:
            return self._normalize_dict(self._first_json("/usersummary-service/stats/im/daily", {"date": date_str}) or self._api("/wellness-service/wellness/intensityMinutes", {"date": date_str}))
        except Exception:
            return {}

    def get_fitnessage_data(self, date_str: str | None = None) -> dict[str, Any]:
        target = date_str or date.today().isoformat()
        try:
            return self._normalize_dict(self._api(f"/fitnessage-service/fitnessage/{target}"))
        except Exception:
            return {}

    def get_body_composition(self, date_str: str) -> dict[str, Any]:
        try:
            return self._normalize_dict(self._first_json("/weight-service/weight/dateRange", {"startDate": date_str, "endDate": date_str}) or self._api("/wellness-service/wellness/bodyComposition", {"date": date_str}))
        except Exception:
            return {}

    def get_weigh_ins(self, start_date: str, end_date: str) -> list[dict[str, Any]]:
        try:
            data = self._first_json("/weight-service/weight/range/%s/%s" % (start_date, end_date), {"includeAll": True})
            if data is None:
                data = self._first_json("/userprofile-service/weight", {"startDate": start_date, "endDate": end_date})
            return self._normalize_list(data)
        except Exception:
            return []

    def get_stats_and_body(self, date_str: str) -> dict[str, Any]:
        stats = self.get_stats(date_str)
        body = self.get_body_composition(date_str)
        body_avg = body.get("totalAverage") if isinstance(body, dict) else {}
        if not isinstance(body_avg, dict):
            body_avg = {}
        return {**stats, **body_avg}

    def get_stats(self, date_str: str) -> dict[str, Any]:
        try:
            return self._normalize_dict(self._api(f"/usersummary-service/usersummary/daily/{self._display_name()}", {"calendarDate": date_str}))
        except Exception:
            return {}

    def get_unit_system(self) -> dict[str, Any]:
        return {"unitSystem": "metric"}

    def get_lactate_threshold(self) -> dict[str, Any]:
        try:
            latest = self._api("/biometric-service/biometric/latestLactateThreshold")
            power = self._api(f"/biometric-service/biometric/powerToWeight/latest/{date.today().isoformat()}", {"sport": "Running"})
            return {"latest": latest, "power": power}
        except Exception:
            return {}

    def get_cycling_ftp(self) -> dict[str, Any]:
        try:
            return self._normalize_dict(self._api("/biometric-service/biometric/latestFunctionalThresholdPower/CYCLING"))
        except Exception:
            return {}

    def get_progress_summary_between_dates(self, start_date: str, end_date: str) -> dict[str, Any]:
        return {}

    def get_last_activity(self) -> dict[str, Any]:
        acts = self.get_activities(0, 1)
        return acts[0] if acts else {}

    def get_weekly_steps(self, end_date: str, weeks: int = 4) -> list[dict[str, Any]]:
        try:
            return self._normalize_list(self._api(f"/usersummary-service/stats/steps/weekly/{end_date}/{weeks}"))
        except Exception:
            return []

    def get_weekly_intensity_minutes(self, start: str, end: str) -> list[dict[str, Any]]:
        try:
            return self._normalize_list(self._api(f"/usersummary-service/stats/im/weekly/{start}/{end}"))
        except Exception:
            return []

    def get_weekly_stress(self, end_date: str, weeks: int = 4) -> list[dict[str, Any]]:
        try:
            return self._normalize_list(self._api(f"/usersummary-service/stats/stress/weekly/{end_date}/{weeks}"))
        except Exception:
            return []

    def get_hill_score(self, date_str: str) -> dict[str, Any]:
        return self._normalize_dict(self._first_json(f"/metrics-service/metrics/hillscore/{date_str}"))

    def get_endurance_score(self, date_str: str) -> dict[str, Any]:
        return self._normalize_dict(self._first_json(f"/metrics-service/metrics/endurancescore/{date_str}"))

    def get_running_tolerance(self, start: str, end: str) -> list[dict[str, Any]]:
        try:
            return self._normalize_list(self._api("/metrics-service/metrics/runningtolerance/stats", {"startDate": start, "endDate": end, "aggregation": "daily"}))
        except Exception:
            return []

    def get_lifestyle_logging_data(self, date_str: str) -> dict[str, Any]:
        try:
            return self._normalize_dict(self._api(f"/lifestylelogging-service/dailyLog/{date_str}"))
        except Exception:
            return {}

    def get_max_metrics(self, date_str: str) -> dict[str, Any]:
        try:
            return self._normalize_dict(self._api(f"/metrics-service/metrics/maxmet/daily/{date_str}/{date_str}"))
        except Exception:
            return {}

    def get_race_predictions(self, startdate: str | None = None, enddate: str | None = None, _type: str | None = None) -> dict[str, Any]:
        if _type is None and startdate is None and enddate is None:
            try:
                return self._normalize_dict(self._api(f"/metrics-service/metrics/racepredictions/latest/{self._display_name()}"))
            except Exception:
                return {}
        if _type is not None and startdate is not None and enddate is not None:
            try:
                return self._normalize_dict(self._api(f"/metrics-service/metrics/racepredictions/{_type}/{self._display_name()}", {"fromCalendarDate": startdate, "toCalendarDate": enddate}))
            except Exception:
                return {}
        raise ValueError("you must either provide all parameters or no parameters")

    def get_gear(self, userProfileNumber: str) -> list[dict[str, Any]]:
        try:
            return self._normalize_list(self._api("/gear-service/gear/filterGear", {"userProfilePk": userProfileNumber}))
        except Exception:
            return []

    def get_gear_defaults(self, userProfileNumber: str) -> dict[str, Any]:
        try:
            return self._normalize_dict(self._api(f"/gear-service/gear/user/{userProfileNumber}/activityTypes"))
        except Exception:
            return {}

    def get_hydration_data(self, date_str: str) -> dict[str, Any]:
        try:
            return self._normalize_dict(self._api(f"/usersummary-service/usersummary/hydration/daily/{date_str}"))
        except Exception:
            return {}

    def get_nutrition_daily_food_log(self, date_str: str) -> dict[str, Any]:
        try:
            return self._normalize_dict(self._api(f"/nutrition-service/food/logs/{date_str}"))
        except Exception:
            return {}

    def get_nutrition_daily_meals(self, date_str: str) -> dict[str, Any]:
        try:
            return self._normalize_dict(self._api(f"/nutrition-service/meals/{date_str}"))
        except Exception:
            return {}

    def get_goals(self) -> list[dict[str, Any]]:
        try:
            return self._normalize_list(self._api("/goal-service/goal/goals"))
        except Exception:
            return []

    def get_earned_badges(self) -> list[dict[str, Any]]:
        try:
            return self._normalize_list(self._api("/badge-service/badge/earned"))
        except Exception:
            return []

    def get_available_badges(self) -> list[dict[str, Any]]:
        try:
            return self._normalize_list(self._api("/badge-service/badge/available"))
        except Exception:
            return []

    def get_adhoc_challenges(self, start: int = 0, limit: int = 20) -> list[dict[str, Any]]:
        try:
            return self._normalize_list(self._api("/adhocchallenge-service/adHocChallenge/historical", {"start": start, "limit": limit}))
        except Exception:
            return []

    def get_badge_challenges(self, start: int = 0, limit: int = 20) -> list[dict[str, Any]]:
        try:
            return self._normalize_list(self._api("/badgechallenge-service/badgeChallenge/completed", {"start": start, "limit": limit}))
        except Exception:
            return []

    def get_personal_record(self) -> list[dict[str, Any]]:
        try:
            return self._normalize_list(self._api("/personalrecord-service/personalrecord/prs"))
        except Exception:
            return []

    def get_in_progress_badges(self) -> list[dict[str, Any]]:
        try:
            return self._normalize_list(self._api("/badgechallenge-service/virtualChallenge/inProgress"))
        except Exception:
            return []

    def get_non_completed_badge_challenges(self) -> list[dict[str, Any]]:
        try:
            return self._normalize_list(self._api("/badgechallenge-service/badgeChallenge/non-completed"))
        except Exception:
            return []

    def get_available_badge_challenges(self) -> list[dict[str, Any]]:
        try:
            return self._normalize_list(self._api("/badgechallenge-service/badgeChallenge/available"))
        except Exception:
            return []

    def get_golf_summary(self) -> dict[str, Any]:
        try:
            return self._normalize_dict(self._api("/golf-service/summary"))
        except Exception:
            return {}

    def get_training_plans(self) -> dict[str, Any]:
        try:
            return self._api("/workout-service/training-plans")
        except Exception:
            return {"trainingPlanList": []}

    def get_workouts(self) -> list[dict[str, Any]]:
        return self._api("/workout-service/workouts", {"start": 0, "limit": 100})

    def get_scheduled_workouts(self, year: int, month: int) -> dict[str, Any]:
        try:
            return self._api("/workout-service/schedules", {"year": year, "month": month})
        except Exception:
            return {"calendarItems": []}

    def create_manual_activity(self, start_datetime: str, time_zone: str, type_key: str, distance_km: float, duration_min: float, activity_name: str) -> dict[str, Any]:
        payload = {
            "startDate": start_datetime,
            "timeZoneId": time_zone,
            "activityTypeDTO": {"typeKey": type_key},
            "distance": distance_km,
            "duration": duration_min,
            "activityName": activity_name,
        }
        return self._api_post("/activity-service/activity", payload)

    def add_weigh_in(self, weight: float, unitKey: str = "kg", date: str | None = None) -> dict[str, Any]:
        payload = {"userData": {"weight": int(weight * 1000), "date": date, "unitKey": unitKey}}
        return self._api_put("/userprofile-service/userprofile/user-settings/", payload)

    def add_hydration_data(self, value_in_ml: float) -> dict[str, Any]:
        payload = {"calendarDate": date.today().isoformat(), "timestampLocal": datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3], "valueInML": value_in_ml}
        try:
            return self._api_post("/usersummary-service/usersummary/hydration/log", payload)
        except Exception:
            return {}

    def add_body_composition(self, **kwargs: Any) -> dict[str, Any]:
        return self._api_post("/upload-service/upload/bodyComposition", kwargs)

    def set_blood_pressure(self, **kwargs: Any) -> dict[str, Any]:
        timestamp = kwargs.get("timestamp")
        dt = datetime.fromisoformat(timestamp) if timestamp else datetime.now()
        dt_gmt = dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        payload = {
            "measurementTimestampLocal": dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3],
            "measurementTimestampGMT": dt_gmt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3],
            "systolic": int(kwargs["systolic"]),
            "diastolic": int(kwargs["diastolic"]),
            "pulse": int(kwargs["pulse"]),
            "sourceType": "MANUAL",
            "notes": kwargs.get("notes", ""),
        }
        try:
            return self._api_post("/bloodpressure-service/bloodpressure", payload)
        except Exception:
            return {}

    def create_workout(self, workout: Any) -> dict[str, Any]:
        payload = self._workout_payload(workout)
        return self._api_post("/workout-service/workout", payload)

    def _workout_payload(self, workout: Any) -> Any:
        if hasattr(workout, "to_dict"):
            return workout.to_dict()
        if hasattr(workout, "model_dump"):
            return workout.model_dump(exclude_none=False)
        if hasattr(workout, "toJson"):
            return workout.toJson()
        return workout

    def upload_workout(self, workout_json: dict[str, Any] | list[Any] | str) -> dict[str, Any]:
        if isinstance(workout_json, str):
            payload = json.loads(workout_json)
        else:
            payload = workout_json
        return self._api_post("/workout-service/workout", payload)

    def upload_running_workout(self, workout: Any) -> dict[str, Any]:
        return self.upload_workout(self._workout_payload(workout))

    def upload_cycling_workout(self, workout: Any) -> dict[str, Any]:
        return self.upload_workout(self._workout_payload(workout))

    def upload_swimming_workout(self, workout: Any) -> dict[str, Any]:
        return self.upload_workout(self._workout_payload(workout))

    def upload_walking_workout(self, workout: Any) -> dict[str, Any]:
        return self.upload_workout(self._workout_payload(workout))

    def upload_hiking_workout(self, workout: Any) -> dict[str, Any]:
        return self.upload_workout(self._workout_payload(workout))

    def schedule_workout(self, workout_id: str, schedule_date: str) -> dict[str, Any]:
        return self._api_post(f"/workout-service/schedule/{workout_id}", {"date": schedule_date})

    def unschedule_workout(self, workout_id: str, schedule_date: str) -> dict[str, Any]:
        return self._api_post(f"/workout-service/schedule/{workout_id}/unschedule", {"date": schedule_date})

    def delete_workout(self, workout_id: str) -> dict[str, Any]:
        return self._api_delete(f"/workout-service/workout/{workout_id}")

    def import_activity(self, file_path: str) -> dict[str, Any]:
        path = Path(file_path)
        ext = path.suffix.lower().lstrip(".")
        with open(path, "rb") as f:
            files = {"userfile": (path.name, f.read())}
        r = self.app_session.post(
            f"https://connect.garmin.cn/gc-api/upload-service/upload/{ext}",
            headers=self._base_headers(),
            files=files,
            timeout=60,
        )
        if r.status_code >= 400:
            raise RuntimeError(f"CN activity import failed: {r.status_code} {r.text[:160]}")
        return r.json() if r.text else {}

    def upload_activity(self, file_path: str) -> dict[str, Any]:
        return self.import_activity(file_path)
