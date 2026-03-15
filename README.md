# wechat-digest

> 监控指定微信群，生成 AI 摘要日报并发送到 Telegram。

## 功能
- 选择要监控的群聊（支持多选，记住上次选择）
- 指定时间范围导出日报（今天 / 最近2天 / 最近3天 / 最近7天）
- 支持任意 AI 模型（Claude、DeepSeek、通义千问、Ollama 等兼容 OpenAI 协议的服务）
- 日报通过 Telegram Bot 发送

## 环境要求
- Windows 10/11
- Python 3.9+
- PC 端微信保持登录状态

## 安装

```bash
git clone https://github.com/你的用户名/wechat-digest.git
cd wechat-digest
pip install -r requirements.txt
```

## 使用步骤

1. 双击 run.bat 启动（或 `python src/app.py`）
2. 展开"AI 模型设置"，填入 API Key 和模型名称，保存
3. 展开"Telegram 设置"，填入 Bot Token 和 Chat ID，测试连接
4. 点击"刷新列表"加载群聊，勾选要监控的群
5. 选择时间范围，点击"生成并发送日报"

## 如何创建 Telegram Bot

1. 在 Telegram 搜索 @BotFather，发送 /newbot，按提示操作获得 Bot Token
2. 给你的 Bot 发一条任意消息
3. 访问 `https://api.telegram.org/bot{你的Token}/getUpdates`，在返回结果中找到 `chat.id`

## 支持的 AI 服务

| 服务 | Provider 选择 | Base URL | 模型名示例 |
|------|-------------|----------|-----------|
| Claude | Anthropic | （自动填入） | claude-sonnet-4-20250514 |
| DeepSeek | OpenAI Compatible | https://api.deepseek.com | deepseek-chat |
| 通义千问 | OpenAI Compatible | https://dashscope.aliyuncs.com/compatible-mode/v1 | qwen-max |
| Ollama | OpenAI Compatible | http://localhost:11434/v1 | llama3 |

## 测试模式（无需微信）

双击 run_mock.bat，使用模拟数据测试完整流程。

## 免责声明

本项目仅供个人学习研究使用，请勿用于监控他人。
使用前请确认符合微信用户协议及当地法律法规，风险自负。

## License

MIT
