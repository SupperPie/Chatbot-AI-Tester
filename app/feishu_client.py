"""
飞书 API 客户端 - 用于导出测试报告到飞书表格
"""
import os
import requests
from typing import List, Dict, Any, Optional
from datetime import datetime

class FeishuClient:
    """飞书开放平台 API 客户端"""
    
    def __init__(self):
        self.app_id = os.getenv("FEISHU_APP_ID")
        self.app_secret = os.getenv("FEISHU_APP_SECRET")
        self.base_url = "https://open.feishu.cn/open-apis"
        self._tenant_access_token = None
        self._token_expires_at = 0
    
    def _get_tenant_access_token(self) -> str:
        """获取 tenant_access_token"""
        import time
        
        # 检查缓存的 token 是否有效
        if self._tenant_access_token and time.time() < self._token_expires_at - 60:
            return self._tenant_access_token
        
        url = f"{self.base_url}/auth/v3/tenant_access_token/internal"
        payload = {
            "app_id": self.app_id,
            "app_secret": self.app_secret
        }
        
        resp = requests.post(url, json=payload)
        data = resp.json()
        
        if data.get("code") != 0:
            raise Exception(f"获取飞书 token 失败: {data.get('msg')}")
        
        self._tenant_access_token = data["tenant_access_token"]
        self._token_expires_at = time.time() + data.get("expire", 7200)
        
        return self._tenant_access_token
    
    def _headers(self) -> Dict[str, str]:
        """获取请求头"""
        return {
            "Authorization": f"Bearer {self._get_tenant_access_token()}",
            "Content-Type": "application/json"
        }
    
    def get_wiki_node_info(self, token: str) -> Dict[str, Any]:
        """获取知识库节点信息，用于获取实际的 spreadsheet token"""
        url = f"{self.base_url}/wiki/v2/spaces/get_node"
        params = {"token": token}
        
        resp = requests.get(url, headers=self._headers(), params=params)
        data = resp.json()
        
        if data.get("code") != 0:
            raise Exception(f"获取知识库节点失败: {data.get('msg')}")
        
        return data.get("data", {}).get("node", {})
    
    def append_rows_to_sheet(
        self, 
        spreadsheet_token: str, 
        sheet_id: str, 
        rows: List[List[Any]]
    ) -> Dict[str, Any]:
        """向表格追加数据行
        
        Args:
            spreadsheet_token: 电子表格 token
            sheet_id: 工作表 ID
            rows: 要追加的数据行，每行是一个列表
        
        Returns:
            API 响应
        """
        url = f"{self.base_url}/sheets/v2/spreadsheets/{spreadsheet_token}/values_append"
        
        # 构建范围，追加到表格末尾
        range_str = f"{sheet_id}!A:Z"
        
        payload = {
            "valueRange": {
                "range": range_str,
                "values": rows
            }
        }
        
        resp = requests.post(url, headers=self._headers(), json=payload)
        data = resp.json()
        
        if data.get("code") != 0:
            raise Exception(f"写入飞书表格失败: {data.get('msg')}")
        
        return data
    
    def get_sheet_meta(self, spreadsheet_token: str) -> Dict[str, Any]:
        """获取电子表格元信息"""
        url = f"{self.base_url}/sheets/v3/spreadsheets/{spreadsheet_token}/sheets/query"
        
        resp = requests.get(url, headers=self._headers())
        data = resp.json()
        
        if data.get("code") != 0:
            raise Exception(f"获取表格元信息失败: {data.get('msg')}")
        
        return data.get("data", {})
    
    def create_sheet(self, spreadsheet_token: str, title: str) -> str:
        """创建新的工作表
        
        Args:
            spreadsheet_token: 电子表格 token
            title: 工作表名称
        
        Returns:
            新创建的 sheet_id
        """
        url = f"{self.base_url}/sheets/v2/spreadsheets/{spreadsheet_token}/sheets_batch_update"
        
        payload = {
            "requests": [
                {
                    "addSheet": {
                        "properties": {
                            "title": title,
                            "index": 0  # 放在最前面
                        }
                    }
                }
            ]
        }
        
        resp = requests.post(url, headers=self._headers(), json=payload)
        data = resp.json()
        
        if data.get("code") != 0:
            raise Exception(f"创建工作表失败: {data.get('msg')}")
        
        # 从响应中获取新创建的 sheet_id
        replies = data.get("data", {}).get("replies", [])
        if replies and replies[0].get("addSheet"):
            return replies[0]["addSheet"]["properties"]["sheetId"]
        
        raise Exception("创建工作表成功但无法获取 sheet_id")


def export_report_to_feishu(
    report_data: List[Dict[str, Any]], 
    spreadsheet_token: str = None,
    sheet_id: str = None,
    wiki_token: str = None,
    api_name: str = "Test",
    create_new_sheet: bool = True
) -> Dict[str, Any]:
    """导出测试报告到飞书表格
    
    Args:
        report_data: 测试报告数据列表
        spreadsheet_token: 电子表格 token（如果是独立表格）
        sheet_id: 工作表 ID
        wiki_token: 知识库文档 token（如果表格在 wiki 中）
        api_name: API 名称，用于生成新 sheet 名称
        create_new_sheet: 是否创建新的工作表（默认 True）
    
    Returns:
        导出结果
    """
    client = FeishuClient()
    
    # 如果是 wiki 中的表格，需要先获取实际的 spreadsheet token
    if wiki_token:
        node_info = client.get_wiki_node_info(wiki_token)
        spreadsheet_token = node_info.get("obj_token")
        if not spreadsheet_token:
            raise Exception("无法获取 wiki 中表格的 token")
    
    # 创建新的工作表，名称为 "API名称_日期"
    if create_new_sheet:
        sheet_title = f"{api_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        sheet_id = client.create_sheet(spreadsheet_token, sheet_title)
    elif not sheet_id:
        # 如果不创建新 sheet 且没有指定 sheet_id，获取第一个工作表
        meta = client.get_sheet_meta(spreadsheet_token)
        sheets = meta.get("sheets", [])
        if sheets:
            sheet_id = sheets[0].get("sheet_id")
        else:
            raise Exception("表格中没有工作表")
    
    # 转换报告数据为行格式（与 report 页面列一致）
    rows = []
    for item in report_data:
        # 处理多轮对话的情况
        if item.get("type") == "multi_turn" and item.get("turns"):
            for turn in item["turns"]:
                score_val = turn.get("score") if turn.get("score") is not None else item.get("score", 0)
                row = [
                    item.get("case_id", ""),
                    turn.get("turn", ""),
                    turn.get("user", ""),
                    turn.get("expected", ""),
                    turn.get("actual", ""),
                    turn.get("retrieval_context", ""),
                    score_val,
                    "Pass" if item.get("passed") else "Fail",
                    turn.get("ttft", 0),
                    turn.get("latency", 0),
                    item.get("reason", ""),
                    "",  # review_comment
                    turn.get("thinking", ""),
                    turn.get("inform_base", ""),
                    str(turn.get("raw", ""))
                ]
                rows.append(row)
        else:
            # 单轮对话
            retrieval_context = item.get("retrieval_context", "")
            if isinstance(retrieval_context, list):
                retrieval_context = ", ".join(str(x) for x in retrieval_context)
            
            row = [
                item.get("case_id", ""),
                "",  # turn_index
                item.get("input", ""),
                item.get("expected_output", ""),
                item.get("actual_output", ""),
                retrieval_context,
                item.get("score", 0),
                "Pass" if item.get("passed") else "Fail",
                item.get("ttft", 0),
                item.get("latency", 0),
                item.get("reason", ""),
                "",  # review_comment
                item.get("thinking", ""),
                item.get("inform_base", ""),
                str(item.get("raw", ""))
            ]
            rows.append(row)
    
    if not rows:
        return {"success": False, "message": "没有数据可导出"}
    
    # 先写入表头（与 report 页面一致）
    headers = [[
        "Case ID", "Turn", "Input", "Expected", "Actual Output", "Retrieval Context",
        "Score", "Passed", "TTFT", "Latency", "Reason", 
        "Review Comment", "Thinking", "Inform Base", "Raw"
    ]]
    client.append_rows_to_sheet(spreadsheet_token, sheet_id, headers)
    
    # 追加数据行
    result = client.append_rows_to_sheet(spreadsheet_token, sheet_id, rows)
    
    return {
        "success": True,
        "message": f"成功导出 {len(rows)} 条记录到飞书表格",
        "rows_count": len(rows),
        "detail": result
    }


def parse_feishu_url(url: str) -> Dict[str, str]:
    """解析飞书表格 URL，提取 token 和 sheet_id
    
    支持格式：
    - https://xxx.feishu.cn/wiki/xxx?sheet=yyy (wiki 中的表格)
    - https://xxx.feishu.cn/sheets/xxx?sheet=yyy (独立表格)
    """
    import re
    from urllib.parse import urlparse, parse_qs
    
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    
    result = {
        "wiki_token": None,
        "spreadsheet_token": None,
        "sheet_id": query.get("sheet", [None])[0]
    }
    
    # 检查是 wiki 还是 sheets
    if "/wiki/" in parsed.path:
        # wiki 格式: /wiki/{wiki_token}
        match = re.search(r'/wiki/([^/?]+)', parsed.path)
        if match:
            result["wiki_token"] = match.group(1)
    elif "/sheets/" in parsed.path:
        # sheets 格式: /sheets/{spreadsheet_token}
        match = re.search(r'/sheets/([^/?]+)', parsed.path)
        if match:
            result["spreadsheet_token"] = match.group(1)
    
    return result
