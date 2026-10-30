# -*- coding=UTF-8 -*-
# @Project          QL_TimingScript
# @fileName         浓五的酒馆.py
# @author           Echo
# @EditTime         2026/10/31  v2.0.0 修复每日签到活动标题匹配（改为模糊匹配）
# const $ = new Env('浓五的酒馆');
# cron: 0 0 10 * * *
"""
【浓五的酒馆 小程序签到】
1. 电脑微信打开【浓五的酒馆】小程序，进入"个人中心-任务中心-每日签到"
2. 开启抓包（如 ProxyPin），点击签到页
3. 抓取 stdcrm.dtmiller.com 请求头中的 authorization 完整值（不要带 Bearer 前缀），填入环境变量 nwjg_token
变量格式： nwjg_token，多个账号用@隔开
token有效期约24小时，失效后需重新抓包
"""
import json
import re
from datetime import datetime

import httpx

import log
from get_env import get_env
from sendNotify import send_notification_message_collection

nwjg_tokens = get_env("nwjg_token", "@")


class Nwjg:
    def __init__(self, token):
        self.user = None
        self.client = httpx.Client(
            verify=False,
            timeout=60
        )
        self.token = token
        self.headers = {
            'xweb_xhr': '1',
            'content-type': 'application/json',
            'sec-fetch-site': 'cross-site',
            'sec-fetch-mode': 'cors',
            'sec-fetch-dest': 'empty',
            'accept-language': 'zh-CN,zh;q=0.9',
            'Authorization': f'Bearer {self.token}'
        }
        self.promotion_id = self.get_promotion_id()

    def get_promotion_id(self):
        try:
            response = self.client.post(
                url="https://stdcrm.dtmiller.com/scrm-promotion-service/mini/module/config/list",
                headers=self.headers,
            )
            if response.status_code != 200:
                log.log(f"获取活动ID失败: HTTP {response.status_code} - {response.text}")
                return None

            response_data = response.json()
            if response_data.get('msg', None) is not None and "JWT expired" in response_data.get('msg'):
                log.log("获取活动ID失败: token已过期！")
                return None

            # 遍历所有模块和detailList，查找title包含'每日签到'的项
            for module in response_data.get('data', []):
                for item in module.get('detailList', []):
                    try:
                        detail_json = json.loads(item['detailJson'])
                        if '每日签到' in str(detail_json.get('title', '')):
                            page_path = detail_json['jumpData']['pagePath']
                            match = re.search(r'promotionId=([^&]*)', page_path)
                            if match:
                                return match.group(1)
                    except Exception as e:
                        log.log(f"解析detailJson异常: {e}")
                        continue

            log.log("未找到每日签到活动")
            return None

        except json.JSONDecodeError:
            log.log("获取活动ID失败: 响应不是有效的JSON格式")
            return None
        except KeyError as e:
            log.log(f"获取活动ID失败: 响应缺少必要字段 - {str(e)}")
            return None
        except Exception as e:
            log.log(f"获取活动ID发生异常: {type(e).__name__} - {str(e)}")
            return None

    def sign(self):
        if not self.promotion_id:
            return 
        self.get_integral()
        try:
            response = self.client.get(
                url="https://stdcrm.dtmiller.com/scrm-promotion-service/promotion/sign/today",
                headers=self.headers,
                params={
                    "promotionId": self.promotion_id
                }
            )
            if response.status_code == 200:
                response_data = response.json()
                if response_data['code'] == 0:
                    log.log(f"用户【{self.user}】 -  签到成功！获得{response_data['data']['prize']['goodsName']} - "
                             f"签到天数： {response_data['data']['signDays']}")
                else:
                    log.log(f"用户【{self.user}】 -  签到失败: {response_data['msg']}")
            else:
                log.log(f"用户【{self.user}】 -  签到失败: {response.text}")
        except Exception as e:
            log.log(f"用户【{self.user}】 -  签到发生异常: {e}")

    def get_integral(self):
        try:
            response = self.client.get(
                url="https://stdcrm.dtmiller.com/scrm-promotion-service/mini/wly/user/info",
                headers=self.headers
            ).json()
            # print(json.dumps(response, indent=4, ensure_ascii=False))
            if response['code'] == 0:
                _mobile = response['data']['member']['mobile'] or ""
                self.user = (_mobile[:3] + "****" + _mobile[-4:]) if len(_mobile) >= 7 else _mobile  # 日志脱敏：前3+****+后4
                log.log(f"用户【{self.user}】 - 当前积分{response['data']['member']['points']}")
            else:
                log.log(f"查询积分失败: {response['msg']}")
        except Exception as e:
            log.log(f"查询积分发生异常: {e}")


if __name__ == '__main__':
    for token in nwjg_tokens:
        nwjg = Nwjg(token)
        nwjg.sign()
    send_notification_message_collection(f"浓五的酒馆签到通知 - {datetime.now().strftime('%Y/%m/%d')}")
