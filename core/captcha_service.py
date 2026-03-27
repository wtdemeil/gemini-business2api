"""
验证码解决服务 - 支持 YesCaptcha 等第三方打码平台

用于解决 Google reCAPTCHA Enterprise，
当 Docker 环境下浏览器自动化触发风控 (CAPTCHA_CHECK_FAILED) 时使用。
"""
import time
import logging
from typing import Optional, Callable

import httpx

logger = logging.getLogger("gemini.captcha")


class CaptchaSolverService:
    """第三方验证码解决服务"""

    def __init__(
        self,
        api_key: str,
        api_url: str = "https://api.yescaptcha.com",
        proxy: str = "",
        log_callback: Optional[Callable] = None,
    ):
        self.api_key = api_key
        self.api_url = api_url.rstrip("/")
        self._log_cb = log_callback
        self._proxy = proxy or None

    def _log(self, level: str, msg: str):
        if self._log_cb:
            self._log_cb(level, msg)
        else:
            getattr(logger, level, logger.info)(msg)

    @property
    def is_available(self) -> bool:
        return bool(self.api_key)

    def _request(self, url: str, payload: dict) -> dict:
        """发送 API 请求（使用 httpx，代理兼容性更好）"""
        with httpx.Client(
            proxy=self._proxy,
            verify=False,
            timeout=30,
        ) as client:
            resp = client.post(url, json=payload)
            resp.raise_for_status()
            return resp.json()

    def solve_recaptcha(
        self,
        site_url: str,
        site_key: str,
        is_enterprise: bool = True,
        max_retries: int = 60,
        initial_delay: float = 5,
        retry_delay: float = 3,
    ) -> Optional[str]:
        """解决 reCAPTCHA 并返回 gRecaptchaResponse token"""
        if not self.api_key:
            return None

        try:
            task_id = self._create_recaptcha_task(site_url, site_key, is_enterprise)
            self._log("info", f"🔑 验证码任务已创建: {task_id}")
            return self._get_task_result(task_id, max_retries, initial_delay, retry_delay)
        except Exception as e:
            self._log("error", f"❌ 验证码解决失败: {e}")
            return None

    def _create_recaptcha_task(
        self, site_url: str, site_key: str, is_enterprise: bool = True
    ) -> str:
        task_type = (
            "RecaptchaV3TaskProxyless"
            if is_enterprise
            else "RecaptchaV3TaskProxyless"
        )
        payload = {
            "clientKey": self.api_key,
            "task": {
                "type": task_type,
                "websiteURL": site_url,
                "websiteKey": site_key,
            },
        }
        data = self._request(f"{self.api_url}/createTask", payload)
        if data.get("errorId") != 0:
            raise Exception(f"创建任务失败: {data.get('errorDescription')}")
        return data["taskId"]

    def _get_task_result(
        self,
        task_id: str,
        max_retries: int = 60,
        initial_delay: float = 5,
        retry_delay: float = 3,
    ) -> Optional[str]:
        time.sleep(initial_delay)

        for i in range(max_retries):
            payload = {"clientKey": self.api_key, "taskId": task_id}
            data = self._request(f"{self.api_url}/getTaskResult", payload)

            if data.get("errorId") != 0:
                raise Exception(f"获取结果失败: {data.get('errorDescription')}")

            status = data.get("status")
            if status == "ready":
                token = data.get("solution", {}).get("gRecaptchaResponse")
                if token:
                    self._log("info", f"✅ 验证码已解决 (轮询 {i + 1} 次)")
                    return token
                raise Exception("返回结果中没有 gRecaptchaResponse")
            elif status == "processing":
                time.sleep(retry_delay)
            else:
                self._log("warning", f"⚠️ 未知状态: {status}")
                time.sleep(retry_delay)

        raise Exception(f"验证码解决超时 (重试 {max_retries} 次)")
