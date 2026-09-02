# SUSTech Schedule Planner

南科大智能课表规划器 — 自动求解无冲突课表，并按 [NCES](https://nces.cra.moe/) 口碑排序。

输入想选的课程，程序会登录 TIS 拉取教学班、智能匹配课名、剪枝低分班级，再枚举所有时间不冲突的方案，帮你优先看到评分更高的组合。

## 两种使用方式

### 方式一：Web 界面（推荐）

适合不想碰 Git / YAML 的同学。

**下载**

- 打开 [GitHub  Releases / Code](https://github.com/zhong12350/sustech-schedule-planner)，点击 **Code → Download ZIP**
- 解压到任意文件夹

**启动**

```bash
python3 run.py
```

浏览器打开 `http://127.0.0.1:5000`：

1. 填写学号与 CAS 密码
2. 添加想选的课程
3. 点击「开始求解」
4. 查看按 NCES 总分排序的无冲突方案

---

### 方式二：命令行

```bash
pip install -r requirements.txt
cp config.yaml.example config.yaml
# 编辑 config.yaml
python src/main.py
```

## 功能特性

- **TIS 自动爬取**：CAS 登录，获取当前学期可选教学班
- **智能课名匹配**：输入「数字信号处理」即可匹配 TIS 长名称；避免 II/III、微系统/嵌入式系统等误匹配
- **冲突求解**：回溯 + MRV + O(1) 冲突检测
- **NCES 评分排序**：对接牛娃课程评价，方案按评分总和排序
- **求解剪枝**：剔除低分教学班、每课保留 top-N，默认最多输出 100 种方案
- **无解诊断**：0 方案时提示哪两门课必然时间冲突
- **Web + CLI**：浏览器或终端均可使用

## 配置说明（命令行）

```yaml
student_id: ""
password: ""

courses:
  - "高等数学（下）"
  - "大学物理（下）"

use_ratings: true
min_rating: 5.0              # NCES 低于此分的班剔除（无评分保留）
max_sections_per_course: 12  # 每门课最多保留多少个班
max_results: 100             # 最多输出多少种方案
```

环境变量：`SUSTECH_SID`、`SUSTECH_PWD`

## 项目结构

```
sustech-schedule-planner/
├── run.py                 # Web 一键启动
├── config.yaml.example
├── requirements.txt
└── src/
    ├── web_app.py         # Flask Web 界面
    ├── main.py            # CLI 入口
    ├── course_match.py    # 智能课名匹配
    ├── filters.py         # 评分剪枝 & 冲突诊断
    ├── ratings.py         # NCES 对接
    ├── scraper.py         # TIS 爬取
    ├── solver.py          # 回溯求解
    ├── display.py         # 终端课表
    ├── pick.py            # 增量选课
    ├── selector.py        # TIS 选课提交
    └── templates/
        └── index.html
```

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
