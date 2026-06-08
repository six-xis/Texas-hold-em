# 德州扑克联机 MVP

联机德州扑克 MVP。游戏仅使用虚拟筹码，不涉及真钱、充值、提现、赌博结算或任何博彩 API。

## 功能状态

- 游客昵称进入游戏，浏览器保存 `guest_id`
- 创建房间、加入房间、离开房间
- 首页显示最近房间列表，可快速加入
- 每个房间最多 20 名成员、20 个座位
- 坐下、站起、准备、房主开始游戏
- 房主可以添加智能机器人，机器人自动入座、准备，并由服务端按简单策略行动
- 游戏开始后自动切换到牌桌视图，展示玩家席位、手牌、公共牌、底池、下注额、行动倒计时和 AI 助手
- 每名玩家行动时间 30 秒，初始 5 张时间卡；超时会自动使用时间卡延长 30 秒，时间卡用完后再次超时自动弃牌
- 房主可以暂停/继续当前牌局，也可以结束当前手牌并退回本局已投入筹码
- 每一手都正常比牌/结算；每 20 手进入一次阶段休息，需要重新准备
- 手牌结束后显示比牌结果弹窗，包含公共牌、底池分配、赢家和摊牌手牌
- 玩家输光后会获得 5000 训练筹码奖励，避免训练局因为 0 筹码无法继续下一手
- 房间聊天区通过 WebSocket 实时同步，保留最近 100 条消息
- FastAPI WebSocket 实时同步房间状态
- 服务端权威处理发牌、行动顺序、下注、all-in、主池/边池和摊牌结算
- 前端展示 20 个座位、公共牌、底池、阶段、当前行动玩家、本人手牌、操作按钮、玩家面板和事件日志
- PostgreSQL/SQLAlchemy 模型和 docker-compose 初始化
- Redis 服务随 docker-compose 启动，预留给后续多进程房间状态和广播

## 参考

本项目的房间流程、事件流展示和客户端状态反馈参考了 [ainilili/ratel](https://github.com/ainilili/ratel) 的事件驱动设计思路。Ratel 使用 Apache-2.0 许可证。本项目没有复制其 Java 实现代码，而是在 FastAPI/WebSocket 架构下独立实现。

当前 MVP 的实时房间状态保存在后端进程内存中。单容器/单进程本地联机可用；如果横向扩容，需要把 `RoomService` 状态迁移到 Redis 或数据库。

## 本地运行

安装依赖：

```bash
python -m pip install -e .[test]
```

启动后端：

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

打开：

```text
http://127.0.0.1:8000
```

如果要用手机访问同一台电脑上的服务，把 `127.0.0.1` 换成电脑的局域网 IP，例如：

```text
http://192.168.x.x:8000
```

电脑和手机需要在同一个局域网内，并允许防火墙放行 8000 端口。

## Docker 运行

启动 PostgreSQL、Redis 和 FastAPI：

```bash
docker compose up --build
```

打开：

```text
http://127.0.0.1:8000
```

停止：

```bash
docker compose down
```

清理数据库卷：

```bash
docker compose down -v
```

## 测试

```bash
python -m pytest
```

测试覆盖：

- 52 张牌、发牌、烧牌、20 人局无重复
- 牌型判断：顺子、同花、葫芦、四条、皇家同花顺等
- A2345 最小顺子、AKQJT 最大顺子
- kicker、两对、葫芦、同花比较
- 多人平局
- fold/check/call/bet/raise/all-in
- all-in 边池分配
- 房间、座位、准备、开局
- HTTP API、WebSocket、页面和静态资源

## WebSocket 事件

客户端只发送意图，服务端广播权威状态。

连接：

```text
ws://127.0.0.1:8000/ws/rooms/{room_code}
```

常用事件：

```json
{"type":"join_room","payload":{"room_code":"ABC123","nickname":"Alice","guest_id":"guest_xxx"}}
{"type":"sit_down","payload":{"seat_index":0}}
{"type":"ready","payload":{"is_ready":true}}
{"type":"start_game","payload":{}}
{"type":"add_bot","payload":{}}
{"type":"pause_game","payload":{"is_paused":true}}
{"type":"end_game","payload":{}}
{"type":"claim_training_chips","payload":{"amount":5000}}
{"type":"send_chat_message","payload":{"content":"大家好"}}
{"type":"use_time_card","payload":{}}
{"type":"player_action","payload":{"action":"call","amount":0}}
```

服务端广播：

```json
{"type":"room_state","revision":2,"payload":{}}
```

错误：

```json
{"type":"action_error","payload":{"code":"INVALID_ACTION","message":"..."}}
```

## 项目结构

```text
app/
  api/
  models/
  poker/
  schemas/
  services/
  static/
  templates/
  config.py
  database.py
  main.py
tests/
Dockerfile
docker-compose.yml
pyproject.toml
```
