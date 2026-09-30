# Boss 直聘薪资字体加密与解密

## 加密原理

Boss 直聘通过自定义 `@font-face`（woff2）将数字 0-9 映射到 Unicode 私用区 U+E031~U+E03A。

## 解密公式 (2026-06-15 修正)

```python
def decrypt_salary(text):
    result = []
    for ch in text:
        cp = ord(ch)
        if 0xE031 <= cp <= 0xE03A:
            result.append(str(cp - 0xE031))
        else:
            result.append(ch)
    return ''.join(result)
```

## 映射表 (2026-06-15 修正)

| Unicode | 解密结果 | 旧版错误 |
|---------|---------|---------|
| U+E031 | 0 | (旧: 1) |
| U+E032 | 1 | (旧: 2) |
| U+E033 | 2 | (旧: 3) |
| U+E034 | 3 | (旧: 4) |
| U+E035 | 4 | (旧: 5) |
| U+E036 | 5 | (旧: 6) |
| U+E037 | 6 | (旧: 7) |
| U+E038 | 7 | (旧: 8) |
| U+E039 | 8 | (旧: 9) |
| U+E03A | 9 | — |

## 旧版错误

旧版使用 `ord(ch) - 0xE030`，导致 **每位数字偏移 +1**（6→被解析为7，21→被解析为32...）。

例如：`\ue036-\ue037K`
- 旧版: 6-7K ❌
- 新版: 5-6K ✅

## 验证数据

| 加密原文 | 旧版结果 | 新版结果 |
|---------|---------|---------|
| `\ue036-\ue037K` | 6-7K ❌ | 5-6K ✅ |
| `\ue039-\ue032\ue033K` | 9-23K ❌ | 8-12K ✅ |

## 影响范围

- 列表页薪资加密 → Phase 1 需解密
- 详情页薪资同样加密 → Phase 3 需解密
- `decrypt_salary()` 已内置到 `phase1_extract.py` 和 `phase3_jd.py`
