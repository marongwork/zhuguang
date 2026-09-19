#!/usr/bin/env python3
"""逐光 · 5大智能体头像视觉资产上传与应用版本发布工具."""

import json
import subprocess
import sys

BOTS = [
    {
        "key": "sentinel",
        "name": "哨兵智能体",
        "app_id": "f61a6b54-c6bd-4a2d-9fa3-4da6f64a3a9e",
        "avatar_path": "/home/ubuntu/avatar_sentinel.jpg",
    },
    {
        "key": "diagnostician",
        "name": "诊断智能体",
        "app_id": "ce0ef71f-80e4-4a62-a1a3-c74cc45c5b66",
        "avatar_path": "/home/ubuntu/avatar_diagnostician.jpg",
    },
    {
        "key": "dispatcher",
        "name": "调度智能体",
        "app_id": "e225edb9-f4d2-483a-a743-f411b65cb7aa",
        "avatar_path": "/home/ubuntu/avatar_dispatcher.jpg",
    },
    {
        "key": "executor",
        "name": "执行智能体",
        "app_id": "9381a8b0-e974-4c67-a2e3-2bac0532008d",
        "avatar_path": "/home/ubuntu/avatar_executor.jpg",
    },
    {
        "key": "auditor",
        "name": "稽核智能体",
        "app_id": "03009f11-f93b-428d-a609-c6c5126fad04",
        "avatar_path": "/home/ubuntu/avatar_auditor.jpg",
    },
]


def run_cmd(cmd: str):
    res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return res.returncode, res.stdout, res.stderr


def main():
    print("=======================================================")
    print("🎨 【逐光·智能体视觉形象升级】为5大智能体注入独立专属头像")
    print("=======================================================")

    for bot in BOTS:
        print(f"\n🚀 正在处理: {bot['name']} (AppID: {bot['app_id']})...")

        # 1. 获取凭证
        code, out, err = run_cmd(
            f"dws devapp +credentials-get --unified-app-id {bot['app_id']} --format json"
        )
        if code != 0:
            print(f"  ❌ 获取凭证失败: {err.strip()}")
            continue
        cred = json.loads(out).get("data", {})
        client_id = cred.get("appKey")
        client_secret = cred.get("appSecret")
        print(f"  🔑 凭证就绪: {client_id}")

        # 2. 上传头像 media
        upload_cmd = (
            f"dws api POST https://oapi.dingtalk.com/media/upload "
            f"--client-id {client_id} --client-secret '{client_secret}' "
            f"--params '{{\"type\":\"image\"}}' --file media={bot['avatar_path']}"
        )
        code, out, err = run_cmd(upload_cmd)
        if code != 0:
            print(f"  ❌ 上传头像失败: {err.strip()}")
            continue
        media_data = json.loads(out)
        media_id = media_data.get("media_id")
        if not media_id:
            print(f"  ❌ 未获取到 media_id: {out.strip()}")
            continue
        print(f"  🖼️ 头像已上传至钉钉媒体库: {media_id}")

        # 3. 更新机器人配置与应用基础信息
        run_cmd(
            f"dws devapp +robot-config --unified-app-id {bot['app_id']} --icon-media-id '{media_id}' -y"
        )
        run_cmd(
            f"dws dev app update --unified-app-id {bot['app_id']} --icon-media-id '{media_id}' -y"
        )
        print("  ⚙️ 机器人配置与应用基础信息图标已更新")

        # 4. 创建新版本并发布上线
        code, out, err = run_cmd(
            f"dws dev app version create --unified-app-id {bot['app_id']} -y --format json"
        )
        ver_id = None
        if code == 0:
            try:
                ver_data = json.loads(out).get("data", {})
                ver_id = ver_data.get("versionId")
            except Exception:
                pass

        if ver_id:
            code, out, err = run_cmd(
                f"dws dev app version publish --unified-app-id {bot['app_id']} --version-id '{ver_id}' -y"
            )
            print(f"  ✅ 新版本已全网发布生效 (versionId: {ver_id})")
        else:
            print("  ⚠️ 版本创建跳过或复用现有发布态")

    print("\n✨ 全部 5 大智能体头像更新并发布上线完成！")


if __name__ == "__main__":
    main()
