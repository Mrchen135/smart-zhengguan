"""Isolated privacy showcase: server-owned synthetic samples, never student records.

Every execution rebuilds its release plan. Neither the browser's preview nor an
arbitrary prompt/payload is trusted as input to the model transport.
"""
import hashlib
import json
from copy import deepcopy
from time import perf_counter
from uuid import uuid4

from django.conf import settings
from django.utils import timezone

from . import llm


POLICY_QUESTION = "硕士开题前通常需要核对哪些培养事项？"
POLICY_EXCERPT = "演示材料：核对个人培养方案、课程与学分完成情况、开题材料和审核流程。具体条件以学校现行正式文件为准。"
SCENARIOS = (
    {"id": "individual", "title": "个体风险分析", "description": "个人画像在校内完成计算", "icon": "user"},
    {"id": "policy", "title": "公开政策问答", "description": "去除身份，只发送公开问题", "icon": "document"},
    {"id": "cohort", "title": "学院汇总分析", "description": "只使用经过检查的统计结果", "icon": "chart"},
    {"id": "small", "title": "小群体保护", "description": "拦截人数过少的统计请求", "icon": "shield"},
)
LABELS = {
    "studentName": "姓名", "studentId": "学号", "phone": "联系电话",
    "supportNote": "个体支持记录", "courseAverage": "课程均分",
    "overdueTasksCount": "逾期任务数", "wellbeingScore": "身心状态指标",
    "question": "提问内容", "publicReference": "公开参考材料",
    "studentCount": "统计人数", "overdueCount": "逾期人数", "completedCount": "按期完成人数",
}
PRIVATE_FIELDS = {"studentName", "studentId", "phone", "supportNote", "wellbeingScore"}


def minimum_group_size():
    return max(5, int(getattr(settings, "PRIVACY_DEMO_MIN_GROUP_SIZE", 5)))


def cloud_available():
    return bool(getattr(settings, "PRIVACY_DEMO_ALLOW_CLOUD", False) and llm.prediction_llm_is_enabled())


def get_catalog():
    return {
        "scenarios": [{**deepcopy(item), "samples": {
            "identified": build_source(item["id"], True), "minimal": build_source(item["id"], False),
        }} for item in SCENARIOS],
        "minimumGroupSize": minimum_group_size(),
        "cloudAvailable": cloud_available(),
        "dataSource": "synthetic",
        "scope": "本展示台只使用虚构样本，不读取学生数据库。隐私策略仅作用于本页任务。",
    }


def build_source(scenario, include_identifiers):
    if scenario not in {item["id"] for item in SCENARIOS}:
        raise ValueError("Unknown privacy scenario")
    identity = {
        "studentName": "演示学生甲", "studentId": "DEMO-001", "phone": "演示号码（非真实）",
        "supportNote": "仅在校内查看的个人支持记录（虚构）",
    } if include_identifiers else {}
    if scenario == "individual":
        return {**identity, "courseAverage": 72, "overdueTasksCount": 2, "wellbeingScore": 64}
    if scenario == "policy":
        question = f"演示学生甲（DEMO-001）想问：{POLICY_QUESTION}" if include_identifiers else POLICY_QUESTION
        return {**identity, "question": question, "publicReference": POLICY_EXCERPT}
    count, overdue = (3, 1) if scenario == "small" else (42, 11)
    return {**identity, "studentCount": count, "overdueCount": overdue, "completedCount": count - overdue}


def inspect_task(scenario, include_identifiers=True):
    source = build_source(scenario, include_identifiers)
    minimum = minimum_group_size()
    route = "local"
    reason = "个体画像与个人支持信息仅在校内处理。"
    payload = None
    if scenario == "policy":
        route = "cloud_eligible"
        reason = "身份信息不外发，使用固定的公开政策问题和演示参考材料。"
        # Reconstruct from public constants, rather than scrubbing arbitrary text.
        payload = {"question": POLICY_QUESTION, "publicReference": POLICY_EXCERPT}
    elif scenario in {"cohort", "small"}:
        counts = [source["studentCount"], source["overdueCount"], source["completedCount"]]
        if all(value == 0 or value >= minimum for value in counts):
            route = "cloud_eligible"
            reason = "统计总人数及非零分组人数均达到阈值，仅允许统计数字外发。"
            payload = {key: source[key] for key in ("studentCount", "overdueCount", "completedCount")}
        else:
            reason = f"统计人数或非零分组人数小于{minimum}人，整个统计请求留在校内。"

    decisions = []
    for field, value in source.items():
        released = payload.get(field) if payload else None
        if route == "local":
            action, explanation = "local", "任务仅在校内执行，不发送云端"
        elif field in PRIVATE_FIELDS:
            action, explanation = "remove", "身份与个体支持字段禁止外发"
        elif field == "question" and value != released:
            action, explanation = "generalize", "替换为不含身份的公开政策问题"
        elif payload is not None and field in payload:
            action, explanation = "keep", "任务所需的公开信息或统计数字"
        else:
            action, explanation = "remove", "不在本任务的外发字段白名单内"
        decisions.append({"field": field, "label": LABELS[field], "action": action,
                          "reason": explanation, "originalValue": value, "releasedValue": released})
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8") if payload else b""
    return {
        "scenario": scenario, "dataSource": "synthetic", "checkedAt": timezone.now().isoformat(),
        "route": route, "reason": reason, "minimumGroupSize": minimum,
        "sourceData": source, "cloudPayload": payload, "decisions": decisions,
        "inputFieldCount": len(source), "protectedFieldCount": sum(row["action"] != "keep" for row in decisions),
        "approvedFieldCount": len(payload or {}), "approvedBytes": len(encoded),
        "payloadDigest": hashlib.sha256(encoded).hexdigest() if encoded else "",
    }


def local_answer(plan):
    scenario, source = plan["scenario"], plan["sourceData"]
    if scenario == "individual":
        return {"directAnswer": "该演示对象有2项逾期任务，建议安排培养事项复核。",
                "reasoning": ["课程均分72分、逾期任务2项，均为虚构样本。", "个人支持记录和身心状态指标留在校内。"],
                "actionPlan": ["核对逾期事项和实际截止时间", "安排导师沟通并约定下次复核时间"], "citations": []}
    if scenario == "policy":
        return {"directAnswer": "开题前可先核对培养方案、课程与学分情况、材料清单及审核流程。",
                "reasoning": ["本地答复依据本页演示参考材料生成。", "具体条件应查阅学校现行正式文件，本页没有作出资格认定。"],
                "actionPlan": ["核对本人培养方案与适用年级", "向学院确认正式材料和办理时间"], "citations": []}
    count, overdue = source["studentCount"], source["overdueCount"]
    if plan["route"] == "local":
        return {"directAnswer": "该统计请求已转为校内处理，未调用云端模型。",
                "reasoning": [plan["reason"], "人数阈值是演示保护措施，不能单独保证匿名化。"],
                "actionPlan": ["在校内查看明细并跟进", "扩大统计范围后重新检查数据边界"], "citations": []}
    return {"directAnswer": f"演示样本共{count}人，其中{overdue}人存在逾期事项，占比{overdue / count:.1%}。",
            "reasoning": [f"按期完成人数为{source['completedCount']}人。", "结果由本地规则计算，仅包含统计数字。"],
            "actionPlan": ["按培养事项梳理共性问题", "将个人跟进名单保留在校内工作台"], "citations": []}


def execute_task(scenario, include_identifiers=True, execution_mode="local"):
    if execution_mode not in {"local", "cloud"}:
        raise ValueError("Unknown execution mode")
    started = perf_counter()
    # Always recompute; never accept a client-provided approved payload.
    plan = inspect_task(scenario, include_identifiers)
    fallback = local_answer(plan)
    answer = fallback
    attempted, used, mode, fallback_reason = False, False, "local", ""
    if execution_mode == "cloud" and plan["route"] == "cloud_eligible":
        if not cloud_available():
            raise ValueError("云端服务尚未启用，请使用本地演示")
        prompt = {
            "messages": [
                {"role": "system", "content": "你是研究生管理演示助手。只根据提供的公开材料或统计数字作答，不推断任何学生身份。明确材料为演示样本，不能作为正式制度或个人资格认定。用中文简洁回答。"},
                {"role": "user", "content": "请解释以下经过隐私检查的演示业务数据，并给出后续建议。"},
            ],
            "structuredInput": plan["cloudPayload"],
        }
        attempted = True
        try:
            result = llm.invoke_prediction_chat_completion(prompt, runtime_options={"timeoutSeconds": 25})
            if result.get("used"):
                candidate = llm.normalize_prediction_chat_answer(result.get("answer"), fallback)
                candidate_json = json.dumps(candidate, ensure_ascii=False)
                private_values = [str(value) for key, value in build_source(scenario, True).items()
                                  if key in PRIVATE_FIELDS and isinstance(value, str)]
                if any(value in candidate_json for value in private_values):
                    fallback_reason = "云端结果未通过隐私复核，已使用本地结果"
                else:
                    answer, used, mode = candidate, True, "cloud"
            else:
                fallback_reason = "云端暂未返回可用结果，已使用本地结果"
        except Exception:
            # Do not return provider errors, credentials or raw response bodies.
            fallback_reason = "云端服务暂不可用，已使用本地结果"
        if not used:
            mode = "fallback"
    elapsed = round((perf_counter() - started) * 1000, 1)
    audit = {
        "requestId": uuid4().hex, "createdAt": timezone.now().isoformat(), "scenario": scenario,
        "executionMode": mode, "cloudAttempted": attempted, "cloudUsed": used,
        "inputFieldCount": plan["inputFieldCount"], "protectedFieldCount": plan["protectedFieldCount"],
        "approvedFieldCount": plan["approvedFieldCount"],
        "payloadDigest": plan["payloadDigest"] if attempted else "", "elapsedMs": elapsed,
    }
    return {"plan": plan, "answer": answer, "audit": audit, "fallbackReason": fallback_reason}
