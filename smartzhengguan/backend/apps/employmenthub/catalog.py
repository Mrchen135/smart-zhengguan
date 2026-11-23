"""Explicit source registry. Disabled entries are navigation links, not live feeds."""

SOURCES = [
    {
        "key": "sdu-selection", "name": "山东大学就业中心 · 各省选调公考",
        "url": "https://job.sdu.edu.cn/xdgk.htm", "province": "全国", "category": "选调生",
        "adapter": "sdu_selection", "enabled": True,
        "metadata": {"coverage": "山大公开转载的各省选调、公考公告；首版读取最近两页", "publisherType": "高校就业中心", "limit": 30},
    },
    {
        "key": "sdu-recruitment", "name": "山东大学就业中心 · 招聘与人才引进",
        "url": "https://jobcareer.sdu.edu.cn/eweb/jygl/index.so?modcode=null&subsyscode=zpfw&type=ssoSearchZxzp",
        "province": "全国", "category": "企业招聘", "adapter": "sdu_recruitment", "enabled": True,
        "metadata": {"coverage": "校就业网公开招聘首屏：企业、事业单位、人才引进；不调用登录接口", "publisherType": "高校就业中心", "limit": 20},
    },
    {
        "key": "sasac-recruitment", "name": "国务院国资委 · 招聘",
        "url": "https://wap.sasac.gov.cn/n2588035/n2588325/n2588350/index.html",
        "province": "全国", "category": "企业招聘", "adapter": "manual", "enabled": False,
        "metadata": {"coverage": "官方入口，尚未接入自动同步", "reason": "当前环境 TLS 证书校验未通过，保留官方入口，不降低证书校验要求"},
    },
    {
        "key": "central-institutions", "name": "人社部 · 中央和国家机关所属事业单位公开招聘",
        "url": "https://www.mohrss.gov.cn/SYrlzyhshbzb/fwyd/SYkaoshizhaopin/zyhgjjgsydwgkzp/",
        "province": "全国", "category": "事业单位", "adapter": "manual", "enabled": False,
        "metadata": {"coverage": "官方入口，尚未接入自动同步", "reason": "公开页面要求浏览器校验，首版不绕过访问校验"},
    },
    {
        "key": "national-civil-service", "name": "国家公务员局 · 考试录用专题",
        "url": "http://bm.scs.gov.cn/kl2027", "province": "全国", "category": "公务员",
        "adapter": "manual", "enabled": False,
        "metadata": {"coverage": "2027 年度官方入口，尚未接入自动同步", "reason": "年度专题与职位附件需单独适配；链接不代表已取得岗位读取权限"},
    },
    {
        "key": "shandong-selection", "name": "灯塔党建在线 · 山东选调公告",
        "url": "https://www.dtdjzx.gov.cn/web/dtdjzx/lyxdszkgg/129480.html", "province": "山东",
        "category": "选调生", "adapter": "manual", "enabled": False,
        "metadata": {"coverage": "山东省官方选调公告入口，尚未接入自动同步", "reason": "目前通过山大公开转载补充，省级栏目待单独适配"},
    },
    {
        "key": "hubei-institutions", "name": "湖北人事考试网 · 事业单位招聘公告",
        "url": "https://rst.hubei.gov.cn/hbrsksw/zlplks/hbssydwzpks/zkgg/index.shtml",
        "province": "湖北", "category": "事业单位", "adapter": "manual", "enabled": False,
        "metadata": {"coverage": "官方入口，尚未接入自动同步", "reason": "当前公开请求返回 HTTP 412，不绕过站点校验"},
    },
    {
        "key": "ncss-jobs", "name": "国家大学生就业服务平台 · 职位信息",
        "url": "https://24365.ncss.cn/student/jobs/index.html", "province": "全国", "category": "企业招聘",
        "adapter": "manual", "enabled": False,
        "metadata": {"coverage": "官方入口，待授权接口接入", "reason": "公开接口指南主要用于高校向平台推送岗位；拉取权限需另行确认"},
    },
    {
        "key": "iguopin-jobs", "name": "国聘 · 招聘信息",
        "url": "https://gpxd.iguopin.com/", "province": "全国", "category": "企业招聘",
        "adapter": "guopin_public", "enabled": True,
        "metadata": {"coverage": "国聘行动公开招聘公告，最近 60 条；企业性质依据国聘公开企业名录。外链公告标明待查看原文。", "publisherType": "公共招聘平台", "limit": 60},
    },
    {
        "key": "netease-campus", "name": "网易官网 · 校园招聘职位",
        "url": "https://campus.163.com/", "province": "全国", "category": "企业招聘",
        "adapter": "netease_campus", "enabled": True,
        "metadata": {"coverage": "从官网当前校招导航发现批次，读取职位职责、要求、地点和投递链接；每批次最多 120 个职位。", "publisherType": "企业招聘官网", "limit": 120},
    },
    {
        "key": "nankai-companies", "name": "南开大学就业中心 · 名企招聘",
        "url": "https://career.nankai.edu.cn/correcruit/index.html", "province": "全国", "category": "企业招聘",
        "adapter": "nankai_company", "enabled": True,
        "metadata": {"coverage": "公开检索阿里、腾讯、字节、美团、京东、百度、快手、小米、小红书、携程、华为、哔哩哔哩等企业，保留近 180 天招聘简章；图片中的条件须查看原文，每轮最多 48 条。", "publisherType": "高校就业中心", "limit": 48},
    },
    {
        "key": "nankai-state-owned", "name": "南开大学就业中心 · 央国企招聘",
        "url": "https://career.nankai.edu.cn/correcruit/index.html", "province": "全国", "category": "企业招聘",
        "adapter": "nankai_company", "enabled": True,
        "metadata": {"coverage": "公开检索国家电网、中国石油、中国石化、华润、中国建筑、中国中铁、中国移动、中国联通、中国电信、国投、中粮、国家能源，保留近 180 天招聘简章；图片中的条件须查看原文，每轮最多 48 条。", "publisherType": "高校就业中心", "limit": 48},
    },
]

# No database-editable host can enlarge this network allowlist.
ADAPTER_HOSTS = {
    "netease_campus": frozenset({"campus.163.com"}),
    "guopin_public": frozenset({"api4.iguopin.com", "gp-api.iguopin.com", "gpxd.iguopin.com"}),
    "nankai_company": frozenset({"career.nankai.edu.cn"}),
    "sdu_selection": frozenset({"job.sdu.edu.cn", "www.job.sdu.edu.cn"}),
    "sdu_recruitment": frozenset({"jobcareer.sdu.edu.cn"}),
}


def seed_sources(update_existing=False):
    """Idempotent explicit command, never run as a side effect of a GET request."""
    from .models import EmploymentSource
    created = 0
    for entry in SOURCES:
        row, is_new = EmploymentSource.objects.get_or_create(
            key=entry["key"], defaults={**{k: v for k, v in entry.items() if k != "key"}, "status": "pending"}
        )
        if update_existing and not is_new:
            adapter_changed = row.adapter != entry["adapter"]
            for key, value in entry.items():
                if key != "key":
                    setattr(row, key, {**row.metadata, **value} if key == "metadata" else value)
            if row.enabled:
                row.metadata.pop("reason", None)
            if adapter_changed:
                row.status, row.last_error = "pending", ""
            row.save()
        created += int(is_new)
    return created
