from nekro_agent.api.plugin import ConfigBase, NekroPlugin
from nekro_agent.core import logger
from nekro_agent.models.db_chat_message import DBChatMessage
from nekro_agent.schemas.agent_ctx import AgentCtx
from nekro_agent.schemas.chat_message import ChatMessage
from nekro_agent.schemas.signal import MsgSignal

plugin = NekroPlugin(
    name="消息回溯",
    module_name="nekro_plugin_message_traceback",
    description="使用 /traceback 或是 /tb 指令实现消息回溯",
    version="0.1.0",
    author="Zaxpris",
    url="https://github.com/zxjwzn/nekro-plugin-memory",
)


@plugin.mount_config()
class PluginConfig(ConfigBase):
    """基础配置"""


async def message_traceback(_ctx: AgentCtx, chatmessage: ChatMessage, args: str) -> None:
    """处理消息回溯指令"""
    logger.info(f"执行消息回溯: {args}")

    # 寻找最近的两条 Bot 消息
    bot_messages = (
        await DBChatMessage.filter(
            chat_key=_ctx.chat_key,
            sender_id="-1",  # Bot 的 sender_id 为 "-1"
            send_timestamp__lt=chatmessage.send_timestamp,
        )
        .order_by("-send_timestamp")
        .limit(2)
    )

    # 如果 Bot 消息少于 2 条，意味着我们要回溯到最初始的状态
    if len(bot_messages) < 2:
        # 删除所有消息
        messages_to_delete = await DBChatMessage.filter(chat_key=_ctx.chat_key)
        count = len(messages_to_delete)
        for msg in messages_to_delete:
            await msg.delete()
        logger.info(f"消息回溯完成，清空了 {count} 条消息。")
        await _ctx.ms.send_text(_ctx.chat_key, message=f"所有 {count} 条对话已被删除", ctx=_ctx, record=False)
        status_message = "当前状态\n等待用户消息..."
        await _ctx.ms.send_text(_ctx.chat_key, message=status_message, ctx=_ctx, record=False)
        return

    # 我们要回溯到倒数第二条 Bot 消息之后
    # bot_messages[0] 是最近的，bot_messages[1] 是倒数第二条
    last_bot_message = bot_messages[1]

    # 删除从上一条 Bot 消息之后到当前指令之间的所有消息
    messages_to_delete = await DBChatMessage.filter(
        chat_key=_ctx.chat_key,
        send_timestamp__gt=last_bot_message.send_timestamp,
        send_timestamp__lte=chatmessage.send_timestamp,
    )

    count = len(messages_to_delete)
    for msg in messages_to_delete:
        await msg.delete()

    logger.info(f"消息回溯完成，删除了 {count} 条消息")
    await _ctx.ms.send_text(_ctx.chat_key, message=f"已回溯到上一条消息，期间的 {count} 条对话已被删除", ctx=_ctx, record=False)
    bot_message_summary = (
        last_bot_message.content_text[:10] + "..."
        if len(last_bot_message.content_text) > 10
        else last_bot_message.content_text
    )
    status_message = f"当前状态\nBOT消息:{bot_message_summary}\n等待用户消息..."
    await _ctx.ms.send_text(_ctx.chat_key, message=status_message, ctx=_ctx, record=False)


COMMAND_MAP = {
    "traceback": message_traceback,
    "tb": message_traceback,
}


@plugin.mount_on_user_message()
async def on_message(_ctx: AgentCtx, chatmessage: ChatMessage) -> MsgSignal:
    msg_text = chatmessage.content_text.strip()

    # 检测是否是指令（以/开头）
    if not msg_text.startswith("/"):
        return MsgSignal.CONTINUE

    # 解析指令和参数
    parts = msg_text[1:].split()  # 移除/前缀并分割
    if not parts:
        return MsgSignal.CONTINUE

    command = parts[0].lower()
    args = " ".join(parts[1:]) if len(parts) > 1 else ""

    # 检查指令是否存在于指令映射中
    if command in COMMAND_MAP:
        try:
            # 执行对应的指令处理函数
            await COMMAND_MAP[command](_ctx, chatmessage, args)
            logger.info(f"成功执行指令: {command}")
        except Exception as e:
            logger.error(f"执行指令 {command} 时发生错误: {e}")
        return MsgSignal.BLOCK_ALL

    # 未知指令，继续处理
    return MsgSignal.CONTINUE

