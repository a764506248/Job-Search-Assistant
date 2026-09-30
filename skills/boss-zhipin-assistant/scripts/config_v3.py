#!/usr/bin/env python3
"""Boss直聘投递 — 统一配置 v5

★ v5 改进（面向 GitHub 通用发布）:
  - 所有用户信息从 profile_loader.py 读取（user_profile.json 为唯一数据源）
  - SEARCH_KEYWORDS 不含城市后缀（city_code 已限定城市，加城市名会漏掉标题不含城市名的岗位）
  - LLM_REVIEW_PROMPT 动态生成，不硬编码任何用户信息
  - 机械预筛只做硬性条件（城市、薪资、大厂、公司名黑名单）
  - 所有行业/岗位语义判断全部交给大模型
  - C_EXCLUDE / T_EXCLUDE 支持 user_profile.json 自定义，否则使用内置通用默认值

变更 v4 → v5:
  - C_EXCLUDE / T_EXCLUDE 内置默认值去除品牌名/行业特定词汇，改为通用化
  - profile_loader 导入 C_EXCLUDE / T_EXCLUDE，用户可在 user_profile.json 中自定义覆盖
  - 内置默认值仅保留猎头/人力外包/房产/保险等跨行业通用排除项
"""

import os
import sys

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SKILL_DIR)

from scripts.profile_loader import (
    USER_NAME, EXPERIENCE, TARGET_CITY, CITY_CODE, MIN_SALARY_K,
    PREFER_NO_BIG_COMPANY, PREFER_NO_HEADHUNTER,
    SEARCH_KEYWORDS, PREFER, AVOID,
    C_EXCLUDE as _USER_C_EXCLUDE,
    T_EXCLUDE as _USER_T_EXCLUDE,
    get_llm_prompt,
)

# ═══════════════════════════════════════════════════════════
# 一、用户画像（从 user_profile.json 读取，禁止硬编码）
# ═══════════════════════════════════════════════════════════

USER = {
    "name": USER_NAME,
    "experience": EXPERIENCE,
    "target_city": TARGET_CITY,
    "city_code": CITY_CODE,
    "min_salary_k": MIN_SALARY_K,
    "prefer_no_big_company": PREFER_NO_BIG_COMPANY,
    "prefer_no_headhunter": PREFER_NO_HEADHUNTER,
}

# ═══════════════════════════════════════════════════════════
# 二、搜索关键词（从 user_profile.json 读取）
# ★ 禁止在关键词中加城市后缀！city_code 已限定城市，
#   在 query 中再加城市名会漏掉标题不含城市名的岗位
# ═══════════════════════════════════════════════════════════

# SEARCH_KEYWORDS 直接从 profile_loader 导入，此处不再重新定义
# 使用方式: from scripts.config_v3 import SEARCH_KEYWORDS

# ═══════════════════════════════════════════════════════════
# 三、机械预筛 —— 只做硬性条件，不做语义判断
# ═══════════════════════════════════════════════════════════

CITY = TARGET_CITY
SALARY_MIN = MIN_SALARY_K
EXCLUDE_SALARY_PATTERNS = ["元/天", "元/时", "元/周"]

BIG_STAGES = ["已上市", "上市公司"]
BIG_SCALES = ["10000人以上", "2000人以上"]

# ═══════════════════════════════════════════════════════════
# 公司名黑名单（内置通用默认值）
# 用户可在 user_profile.json 的 c_exclude 字段中自定义覆盖
# 内置默认值仅排除跨行业的猎头/人力外包/房产/保险等，不含特定品牌名
# ═══════════════════════════════════════════════════════════
_C_EXCLUDE_DEFAULT = [
    "人力", "人力资源", "猎头", "劳务", "外包", "派遣",
    "招聘", "人才", "职业介绍", "企管", "管理咨询",
    "RPO", "聘选", "伯乐", "慧聘", "猎才", "优才",
    "我爱我家", "链家", "贝壳", "德佑", "中原地产",
    "房产", "地产", "不动产",
    "平安人寿", "太平洋保险", "泰康人寿", "中国人寿",
    "保险",
]

# ★ 如果用户在 user_profile.json 中定义了 c_exclude，则使用用户定义；
#    否则使用内置通用默认值
C_EXCLUDE = _USER_C_EXCLUDE if _USER_C_EXCLUDE is not None else _C_EXCLUDE_DEFAULT

# ═══════════════════════════════════════════════════════════
# 标题硬排除词（内置通用默认值）
# 用户可在 user_profile.json 的 t_exclude 字段中自定义覆盖
# 内置默认值仅排除跨行业的低相关度岗位，不含行业特定词汇
# ═══════════════════════════════════════════════════════════
_T_EXCLUDE_DEFAULT = [
    # 基础服务岗
    "保安", "保洁", "服务员", "前台", "收银", "接待",
    "洗碗", "洗菜", "切配", "打荷", "传菜",
    "客服", "导购", "理货", "打包员",
    # 手艺岗
    "厨师", "烘焙", "面点", "裱花",
    "美甲", "美发", "采耳", "足疗", "按摩", "化妆",
    "调酒", "咖啡师",
    # 销售岗
    "销售代表", "电话销售", "房产销售", "房产中介", "房产经纪人",
    "地推", "拉新", "电销",
    # 其他
    "主播", "直播", "网红", "兼职", "小时工", "临时",
    "实习生", "管培生", "储备干部", "小白", "学徒",
    "暑期工", "暑假工", "寒假工",
    "快递", "外卖骑手", "网约车", "驾驶员", "司机", "配送", "骑手",
    "行政", "文员", "出纳", "会计",
    "仓管", "库管", "搬运", "普工", "手工活",
    "装修", "施工", "监理",
    "代理", "加盟",
]

T_EXCLUDE = _USER_T_EXCLUDE if _USER_T_EXCLUDE is not None else _T_EXCLUDE_DEFAULT

# ═══════════════════════════════════════════════════════════
# 四、LLM 审核提示词（动态生成，不硬编码用户信息）
# ═══════════════════════════════════════════════════════════

LLM_REVIEW_PROMPT = get_llm_prompt()
