# SUSTech Schedule Planner

南科大智能课表规划器 — 自动求解无冲突课表，按 [NCES](https://nces.cra.moe/) 口碑排序，并支持课表偏好与可行动建议。

输入想选的课程（或简称如「高数」「线代」），程序会登录 TIS 拉取教学班、匹配课名、剪枝低分班级，再枚举所有满足偏好约束的无冲突方案。

## 两种使用方式

### 方式一：Web 界面（推荐）

适合不想碰 Git / YAML 的同学。

**下载**

- 打开 [GitHub Releases / Code](https://github.com/zhong12350/sustech-schedule-planner)，点击 **Code → Download ZIP**
- 解压到任意文件夹

**启动**

```bash
pip install -r requirements.txt
python3 run.py
```

浏览器打开 `http://127.0.0.1:5000`：

1. 填写学号与 CAS 密码
2. 添加想选的课程（支持简称，见下方课名知识库）
3. 可选：勾选课表偏好（不上早八、连堂上限、空天等）
4. 点击「开始求解」
5. 查看按 NCES 总分与偏好排序的无冲突方案

---

### 方式二：命令行

```bash
pip install -r requirements.txt
cp config.yaml.example config.yaml
# 编辑 config.yaml
python src/main.py
```

增量选课（基于已选课程补一门）：

```bash
python src/pick.py
```

## 功能特性

### 核心

- **TIS 自动爬取**：CAS 登录，获取当前学期六种选课类型的全部教学班
- **智能课名匹配**：模糊匹配 TIS 长名称；处理 II/III、与/和/及 等易混情况
- **课名知识库**：`tis_course_aliases.yaml` 支持「高数 → 高等数学（下）」等南科大常见简称
- **冲突求解**：回溯 + MRV + O(1) 冲突检测
- **NCES 评分排序**：对接牛娃课程评价，方案按评分总和排序
- **求解剪枝**：剔除低分教学班、每课保留 top-N，默认最多 100 种方案

### 课表偏好

从「算可行解」升级为「算更适合你的解」：

| 偏好 | 说明 |
|------|------|
| 不上早八 | 剔除第 1 节教学班 |
| 连堂上限 | 同一天连续上课不超过 N 节 |
| 每周空天 | 至少 N 天完全没有课 |
| 地点相近 | 排序时优先同一天教学楼分区接近（软约束） |

Web 界面可勾选；CLI 在 `config.yaml` 的 `preferences` 段配置。

### 无解时的可行动建议

0 方案时不只报冲突，还会尝试：

- 移除某门课可恢复多少方案
- 切换课程身份（如不同院系的同名课）可恢复多少方案
- 放宽偏好可恢复多少方案

## 课名知识库（两层）

教务系统里已有全校课表，知识库分两层维护：

| 层 | 文件 | 维护方式 |
|----|------|----------|
| 全校课名索引 | `data/catalogs/{学年}-{学期}.yaml` | 脚本自动导出 |
| 简称别名表 | `tis_course_aliases.yaml` | 手动维护 ~20–50 条 |

**每学期初导出索引：**

```bash
python scripts/export_tis_catalog.py
```

在生成的 catalog 里查正式课名，把同学常打的简称写入 `tis_course_aliases.yaml`。匹配失败会记录到 `data/match_misses.log`，方便学期中补充。

## 配置说明（命令行）

```yaml
student_id: ""
password: ""

courses:
  - "高数"          # 可在 tis_course_aliases.yaml 中配置别名
  - "大学物理（下）"

use_ratings: true
min_rating: 5.0
max_sections_per_course: 12
max_results: 100

preferences:
  no_early_morning: false
  max_consecutive_periods: 0   # 0 = 不限制
  min_free_days: 0             # 0 = 不限制
  prefer_nearby_locations: false
```

环境变量：`SUSTECH_SID`、`SUSTECH_PWD`

## 项目结构

```
sustech-schedule-planner/
├── run.py                      # Web 一键启动
├── tis_course_aliases.yaml     # 课名简称知识库
├── config.yaml.example
├── requirements.txt
├── scripts/
│   └── export_tis_catalog.py   # 从 TIS 导出全校课名索引
└── src/
    ├── web_app.py              # Flask Web 界面
    ├── main.py                 # CLI 入口
    ├── aliases.py              # 别名加载与 catalog 导出
    ├── course_match.py         # 智能课名匹配
    ├── preferences.py          # 课表偏好
    ├── filters.py              # 剪枝、冲突诊断、修复建议
    ├── ratings.py              # NCES 对接
    ├── scraper.py              # TIS 爬取
    ├── solver.py               # 回溯求解
    ├── display.py              # 终端课表
    ├── pick.py                 # 增量选课
    ├── selector.py             # TIS 选课提交
    └── templates/
        └── index.html
```

## 开发与 CI

```bash
python -m pytest tests/ -q
```

推送到 `main` 或提交 Pull Request 时，GitHub Actions 会自动运行测试（见 `.github/workflows/ci.yml`）。

## 隐私与安全

- 凭据仅用于登录 TIS；Web 版不持久化密码
- `config.yaml` 已在 `.gitignore` 中
- 请求仅发往南科大官方服务器与 NCES

## 作者

**Yunqi Zhong** ([@zhong12350](https://github.com/zhong12350))

## 免责声明

仅供学习研究使用。使用本工具产生的后果由用户自行承担。

## License

MIT — 见 [LICENSE](LICENSE)
