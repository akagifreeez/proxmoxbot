# Proxmox Discord Bot

Discordサーバーから直接Proxmox仮想マシン(VM)を管理するためのBotです。VMの一覧表示、作成、起動、停止、スペック変更、削除、そしてステータス監視を行うことができます。

## 機能

- **VM一覧表示**: Proxmoxノード上の全VMとステータスを表示します。
- **VM詳細情報**: 特定のVMの詳細スペックとステータスを確認できます。
- **VM作成**: テンプレートからVMをクローンして作成します。
- **リソース変更**: VMのCPUコア数とメモリを変更します。
- **電源管理**: VMの起動と再起動を行います。
- **VM削除**: VMを削除します（安全のため停止後に削除）。
- **監視**: 指定したVMのステータスを定期的にチェックし、停止している場合は通知を送信します。
- **アクセス制御**: 特定のDiscordカテゴリ内でのみコマンドを使用できるように制限します。

## 前提条件

- Python 3.8以上
- Proxmox VE サーバー
- Discord Bot Token

## インストール方法

1.  リポジトリをクローンします:
    ```bash
    git clone <repository_url>
    cd <repository_name>
    ```

2.  必要なPythonパッケージをインストールします:
    ```bash
    pip install discord.py proxmoxer urllib3
    ```

3.  Botの設定を行います:
    - `config.py.example` を `config.py` にリネームします。
    - `config.py` を開き、DiscordとProxmoxの認証情報を入力します。

    ```python
    # config.py

    # --- Discord設定 ---
    DISCORD_TOKEN = 'あなたのDiscord_Bot_Token'
    GUILD_ID = 123456789012345678         # サーバーID
    ALLOWED_CATEGORY_ID = 123456789012345678  # コマンド操作を許可するカテゴリID
    ALERT_CHANNEL_ID = 123456789012345678     # 通知先チャンネルID

    # --- Proxmox設定 ---
    PROXMOX_HOST = '192.168.1.100'
    PROXMOX_USER = 'root@pam'
    PROXMOX_TOKEN_NAME = 'bot'
    PROXMOX_TOKEN_VALUE = 'xxxxx-xxxxx-xxxxx'
    NODE_NAME = 'pve'

    # --- 監視設定 ---
    # 監視対象のVMIDリスト (ここに書いたIDは死活監視されます)
    MONITOR_VM_IDS = [100, 101, 105]
    ```

## 使用方法

PythonでBotを起動します:

```bash
python bptcode.py
```

### コマンド

すべてのコマンドはスラッシュコマンド (`/`) です。

- `/list`: VMの一覧とステータスを表示します。
- `/info <vmid>`: VMの詳細情報（CPU、メモリ、稼働時間など）を表示します。
- `/create <template_id> <new_vmid> <name>`: テンプレートをクローンして新しいVMを作成します。
- `/resize <vmid> <cores> <memory_mb>`: VMのCPUコア数とメモリ(MB)を変更します。変更は再起動後に適用されます。
- `/start <vmid>`: 停止しているVMを起動します。
- `/reboot <vmid>`: 稼働中のVMを再起動します。
- `/delete <vmid>`: VMを削除します。**警告**: この操作は取り消せません。

## 権限

このBotは `config.py` の `ALLOWED_CATEGORY_ID` で指定されたDiscordカテゴリ内でのみ使用できるように制限されています。指定されたカテゴリ内のチャンネルでコマンドを実行してください。

## 監視機能

Botは1分ごとにバックグラウンドタスクを実行し、`MONITOR_VM_IDS` にリストされたVMのステータスをチェックします。監視対象のVMが停止している場合、`ALERT_CHANNEL_ID` にアラートが送信されます。
