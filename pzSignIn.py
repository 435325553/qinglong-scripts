# -*- coding=UTF-8 -*-
# @Project          QL_TimingScript
# @fileName         pzSignIn.py
# @author           Echo
# @EditTime         2026/10/31
# @Version          v2.0.0
# const $ = new Env('品赞代理签到');
# cron: 0 0 9 * * 1
#
# ===== 脚本说明（v2.0.0 重写） =====
# 品赞(ipzan)代理每日签到领金币。
# 需要配置环境变量 pz_account，多个账号用 @ 分隔，支持两种格式：
#   1) Token 直签：
#      填品赞官网登录后浏览器 localStorage 里的 TOKEN（JWT，eyJ... 开头）
#      获取方法：登录 www.ipzan.com → 按F12 → Application → Local Storage
#               → https://www.ipzan.com → TOKEN → 复制整串
#      例：pz_account = "eyJhbGciOiJIUzM4NCIsInR5cCI6IkpXVCJ9.xxx.yyy"
#      （token 有效期 7 天，过期需重新复制更新）
#   2) 手机号#密码（推荐，每次运行自动登录换 token，永不过期）：
#      例：pz_account = "13800138000#我的密码"
#      多个账号：pz_account = "13800138000#密码1@13900139000#密码2"
#      ★ 登录账号必须是品赞注册手机号（11位），不是用户名/昵称。
#
# 说明：品赞登录接口 users-login 的 account 参数不是明文账号，
#       服务端要求 混淆( Base64(手机号 + "QWERIPZAN1290QWER" + 密码) ) 格式，
#       本脚本已按官网前端逻辑复刻该算法（ca00.encode + 随机串打散）。
#       已验证：直接调接口登录无需图形验证码（验证码仅前端UI校验），
#       混淆算法与当前服务端完全兼容（2026/10/31 实测登录成功）。
# ==============================
import base64
import random
from datetime import datetime

import httpx

import log
from get_env import get_env
from sendNotify import send_notification_message_collection

BASE_URL = "https://service.ipzan.com"
SOURCE = "ipzan-home-one"
SALT = "QWERIPZAN1290QWER"


def obfuscate_account(phone, password):
    """
    复刻品赞前端登录 account 混淆算法：
    raw = 手机号 + "QWERIPZAN1290QWER" + 密码
    b64 = Base64(raw)
    随机串 t（80 段随机 hex，模拟 Math.random().toString(16).slice(2)）
    account = t[:100] + b64[:8] + t[100:200] + b64[8:20] + t[200:300] + b64[20:] + t[300:400]
    """
    raw = f"{phone}{SALT}{password}"
    b64 = base64.b64encode(raw.encode("utf-8")).decode("utf-8")
    t = ""
    # 模拟 JS: Math.random().toString(16).slice(2)，每段取浮点数的十六进制小数部分
    while len(t) < 400:
        frac = float(random.random()).hex().split("p")[0]  # 形如 0x0.1a2b3c
        digits = frac.split(".")[1] if "." in frac else frac[2:]
        t += digits
    return t[:100] + b64[:8] + t[100:200] + b64[8:20] + t[200:300] + b64[20:] + t[300:400]


class PzSignIn:
    def __init__(self, credential):
        self.client = httpx.Client(base_url=BASE_URL, verify=False, timeout=30)
        self.token = None
        credential = credential.strip()
        if credential.startswith("eyJ"):
            # Token 直签模式
            self.token = credential
            log.log("使用 Token 直签模式")
        elif "#" in credential:
            # 手机号#密码 模式：自动登录换 token
            phone, password = credential.split("#", 1)
            self.login(phone.strip(), password.strip())
        else:
            log.log(f"凭据格式无法识别（应为 Token 或 手机号#密码）: {credential[:12]}***")

    def login(self, phone, password):
        """品赞登录，换取 JWT token"""
        try:
            response = self.client.post(
                "/users-login",
                json={"account": obfuscate_account(phone, password), "source": SOURCE},
            )
            data = response.json()
            token = (data.get("data") or {}).get("token")
            if token:
                self.token = token
                log.log("=" * 30 + "登录成功，开始执行签到" + "=" * 30)
            else:
                log.log(f"登录失败: {data.get('message', '未知错误')}")
        except Exception as e:
            log.log(f"登录异常: {e}")

    def get_balance(self):
        """获取品赞余额"""
        try:
            r = self.client.get(
                "/home/userWallet-find", headers={"Authorization": self.token}
            ).json()
            return str((r.get("data") or {}).get("balance", "?"))
        except Exception as e:
            log.log(f"查询余额异常: {e}")
            return "?"

    def sign_in(self):
        """品赞签到（领取金币）"""
        if not self.token:
            log.log("无有效 Token，跳过签到")
            return
        try:
            r = self.client.get(
                "/home/userWallet-receive", headers={"Authorization": self.token}
            ).json()
            if r.get("status") == 200 and r.get("data") == "领取成功":
                log.log("签到成功")
                log.log("=" * 100)
                log.log("当前账户余额： " + self.get_balance())
            elif r.get("code") == -1:
                log.log(r.get("message", "签到失败"))
                log.log(f"当前账户余额：{self.get_balance()}")
            else:
                log.log("签到失败！")
                log.log(r)
        except Exception as e:
            log.log(f"签到异常: {e}")


if __name__ == "__main__":
    accounts = get_env("pz_account", "@")
    for credential in accounts:
        pz = PzSignIn(credential)
        pz.sign_in()
        del pz
    send_notification_message_collection("品赞代理签到通知 - " + datetime.now().strftime("%Y/%m/%d"))
