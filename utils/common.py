import discord
import config

def check_access(interaction: discord.Interaction) -> str | None:
    """
    Checks if the command is being invoked in an allowed category.
    コマンドが許可されたカテゴリ内で実行されているかを確認します。

    Args:
        interaction (discord.Interaction): The interaction object representing the command invocation.
            コマンド呼び出しを表すインタラクションオブジェクト。

    Returns:
        str | None: An error message if the access is denied, or None if allowed.
            アクセスが拒否された場合はエラーメッセージ、許可された場合はNone。
    """
    # カテゴリIDチェック
    category_id = getattr(interaction.channel, 'category_id', None)

    # config.ALLOWED_CATEGORY_ID と比較
    if category_id != config.ALLOWED_CATEGORY_ID:
        return "❌ このコマンドは指定された管理カテゴリ内のチャンネルでのみ使用可能です。"
    return None
