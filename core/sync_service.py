"""
Token 同步服务

- 自动同步：刷新 token 成功后自动推送 token 字段到远程服务器
- 手动同步：从前端触发，发送账户全量字段，远程不存在则新增
"""

import logging
from typing import List

import httpx

from core.config import config

logger = logging.getLogger("gemini.sync")

# 自动刷新后同步的字段（仅 token 相关）
TOKEN_FIELDS = [
    "secure_c_ses", "host_c_oses", "csesidx", "config_id",
    "expires_at", "disabled",
]

# 手动同步的全量字段（支持远程新增账号）
ALL_FIELDS = TOKEN_FIELDS + [
    "mail_provider", "mail_address", "mail_password",
    "mail_client_id", "mail_refresh_token", "mail_tenant",
    "mail_base_url", "mail_jwt_token", "mail_verify_ssl",
    "mail_domain", "mail_api_key", "trial_end",
]


def _get_sync_config():
    """获取同步配置，返回 (server_url, headers) 或 None"""
    server_url = (config.basic.sync_server_url or "").strip().rstrip("/")
    server_key = (config.basic.sync_server_key or "").strip()
    if not server_url:
        return None
    headers = {}
    if server_key:
        headers["Authorization"] = f"Bearer {server_key}"
    return server_url, headers


async def _post_sync(client: httpx.AsyncClient, server_url: str, headers: dict, payload: dict) -> dict:
    """发送单个同步请求，返回结果 dict"""
    account_id = payload.get("account_id", "unknown")
    try:
        resp = await client.post(
            f"{server_url}/api/sync-account",
            json=payload,
            headers=headers,
        )
        if resp.status_code == 200:
            data = resp.json()
            action = data.get("action", "updated")
            logger.info(f"[SYNC] 同步成功 ({action}): {account_id}")
            return {"success": True, "account_id": account_id, "action": action}
        else:
            msg = f"status={resp.status_code}, body={resp.text[:200]}"
            logger.warning(f"[SYNC] 同步失败: {account_id}, {msg}")
            return {"success": False, "account_id": account_id, "error": msg}
    except Exception as e:
        logger.warning(f"[SYNC] 同步异常: {account_id}, error={e}")
        return {"success": False, "account_id": account_id, "error": str(e)}


async def sync_account_to_server(account_id: str, config_data: dict) -> bool:
    """
    自动同步：刷新后推送 token 字段。失败不抛异常。
    """
    sync_cfg = _get_sync_config()
    if not sync_cfg:
        return False

    server_url, headers = sync_cfg
    payload = {"account_id": account_id}
    for field in TOKEN_FIELDS:
        if field in config_data:
            payload[field] = config_data[field]

    async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
        result = await _post_sync(client, server_url, headers, payload)
        return result["success"]


async def sync_accounts_to_server(account_ids: List[str]) -> List[dict]:
    """
    手动同步：发送账户全量字段到远程服务器。远程不存在则新增。

    Args:
        account_ids: 要同步的账户 ID 列表

    Returns:
        每个账户的同步结果列表
    """
    sync_cfg = _get_sync_config()
    if not sync_cfg:
        return [{"success": False, "account_id": aid, "error": "未配置同步服务器地址"} for aid in account_ids]

    server_url, headers = sync_cfg

    # 加载本地账户数据
    from core.account import load_accounts_from_source
    all_accounts = load_accounts_from_source()
    accounts_map = {acc.get("id"): acc for acc in all_accounts}

    results = []
    async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
        for account_id in account_ids:
            acc = accounts_map.get(account_id)
            if not acc:
                results.append({"success": False, "account_id": account_id, "error": "本地账号不存在"})
                continue

            payload = {"account_id": account_id}
            for field in ALL_FIELDS:
                if field in acc:
                    payload[field] = acc[field]

            result = await _post_sync(client, server_url, headers, payload)
            results.append(result)

    return results
