# 校园防蚊协同排查系统（参赛原型）

面向 2026 年第十四届全国大学生数字媒体科技作品及创意竞赛的应用开发作品。根据本届报名分类截图，建议申报「自主命题—移动与网络应用开发」，最终以报名系统要求为准。

本项目借鉴用户提供的「愈见山水」运营后台**形式与技术架构**：Django + SimpleUI 中文管理后台、数据库和公众页面；不修改、不连接愈见山水原站。主题是基孔肯雅热等蚊媒传染病的环境预防，不提供疾病诊断、疫情监测或官方上报服务。

## 功能架构

- 校园端：`/` 是区域消杀地图与宿舍登记两大主功能。地图使用用户提供的广东医科大学东莞校区 2025 版底图，叠加饭堂、宿舍楼等点位；显示最近处理时间、后台设定的复查间隔及记录。点位坐标是近似演示值，需校方核实。
- 宿舍端：按批次和房号统计蚊片领取情况，未领取房间保留在清单；领取和宿舍处理是独立事项。处理照片提交后先进入待核对，后台通过后才计入“已处理”。前端不提供点燃蚊香/烟雾的操作指导，只登记经校方允许的措施。
- 隐患上报：`/report.html` 可提交积水隐患线索，现场照片选填、单张、5MB 以内，并通过随机编号查询进度。
- 运营后台：`/admin/`，需要管理员登录；可管理校园区域、处理记录、宿舍房间、发放批次、宿舍领取/处理登记和积水线索。宿舍处理凭证和上报照片只能由有相应权限的后台人员查看。
- SQLite 数据库：登记数据写入服务器。浏览器仅保存本机提交的随机查询编号；API 不提供公开的全量隐患记录列表。
- 接口：`GET /api/areas/`、`GET /api/dorms/` 提供地图/房间状态；`POST /api/dorm-records/` 提交宿舍记录，`GET /api/dorm-records/<随机编号>/` 查询本人提交状态；另有 `POST /api/reports/` 和 `GET /api/reports/<随机编号>/`。

## 本地运行（Windows / Python 3.12）

在项目根目录执行：

```powershell
py -V:Astral/CPython3.12.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py createsuperuser
.\.venv\Scripts\python.exe manage.py seed_demo
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8765
```

上面的首行适用于当前这台电脑；若其他电脑已通过标准 Python 启动器安装 3.12，可改用 `py -3.12 -m venv .venv`。

然后访问：

- 校园端：<http://127.0.0.1:8765/>
- 积水隐患上报：<http://127.0.0.1:8765/report.html>
- 后台：<http://127.0.0.1:8765/admin/>

## Render 免费演示部署

仓库根目录的 `render.yaml` 声明了新建 Render Blueprint 所需的免费 Django Web Service 和 PostgreSQL 数据库。将项目推送到你有权连接的 GitHub 仓库后，在 Render Dashboard 选择 **New → Blueprint** 并连接该仓库。部署会自动生成 Django 密钥和初始后台密码；后台用户名为 `12244221chl`，随机密码可在 Render 服务的 Environment 页面查看。不要复用本地弱密码。

此配置仅供短期竞赛演示：Render 免费 Web Service 空闲 15 分钟会休眠，实例文件系统重启/重新部署后会清空；所以用户上传的照片可能丢失。免费 PostgreSQL 数据库在创建 30 天后到期，且无备份。**不要录入真实个人信息或依赖这套免费环境保存正式业务数据。**

`seed_demo` 会以幂等方式创建地图演示点位、9 栋少量示例房间和一个演示登记批次；**不会**伪造消杀、领取或处理记录。页面会注明地图位置/房间清单仅为演示。正式演示前应在后台按学校授权信息导入准确楼栋房间清单，并由管理员录入真实的处理记录。

宿舍登记演示：在“宿舍领取登记”中按房号提交领取记录，或提交附照片的处理凭证；管理员在后台逐条核对，只有核对通过的记录才更新统计。积水线索演示仍可在 `/report.html` 提交虚构环境线索并由管理员更新状态。

原来 `dist/index.html` 是纯浏览器本机存储的旧管理原型，现保留源码供对比，**不是新的数据库后台**。旧版浏览器 `localStorage` 中的线索和点位不会自动迁入 Django；没有删除这些原始记录。

## 安全与参赛边界

- 这是本地竞赛演示系统，仍不是原生微信小程序，也未接入学校正式流程。不要填个人健康信息或真实患者信息。
- 照片只用于展示环境隐患，避免拍到人脸、证件等个人信息。`media/` 目录属于本地运行数据，重新部署或迁移时需单独备份；正式上线还需要存储与访问安全审查。
- 用随机编号查询单条线索是原型方案，不等于生产级权限体系；上线前还需要账号/权限设计、频率限制、内容审核、数据保留与删除机制、部署安全配置、校方授权及实地验证。
- 演示数据不得当作真实疫情风险。若使用真实校园点位、照片或调查结果，先取得必要授权并做好脱敏。
- 按赛事要求准备运行文件、说明文档、演示视频、原创贡献证明和 AI 工具使用说明。

竞赛通知：[数媒竞赛官网](https://www.cmit.cn/html/tongzhigonggao/show-144-45826-1.html)。防护内容参考：[中国疾病预防控制中心](https://www.chinacdc.cn/jkts/202508/t20250801_309120.html)。

## 主要文件

- `config/`、`mosquito/`、`manage.py`、`requirements.txt`：Django 配置、模型、API、SimpleUI 后台和演示数据命令。
- `dist/dashboard.html`、`dist/dashboard.css`、`dist/dashboard.js`：校园地图与宿舍登记主页面。
- `dist/report.html`、`dist/report.css`、`dist/report.js`：积水隐患上报页。
- `dist/index.html`、`dist/styles.css`、`dist/app.js`：保留的旧本机演示页。
- `source/`：原始 C 程序及需求材料。
