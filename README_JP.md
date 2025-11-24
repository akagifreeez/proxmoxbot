# Proxmox Discord Bot

Discordサーバーから直接Proxmox仮想マシン(VM)およびLXCコンテナを管理するためのBotです。リソースの一覧表示、作成、起動、停止、スペック変更、削除、そしてステータス監視を簡単に行うことができます。

## 機能

- **リソース対応**: **QEMU VM** と **LXC コンテナ** の両方をサポートしています。
- **リソース一覧表示**: Proxmoxノード上の全VM/コンテナとステータス、種類を表示します。
- **詳細情報**: 特定のリソースの詳細スペックとステータスを表示し、インタラクティブな操作ボタンを提供します。
- **VM作成**: テンプレートからVMをクローンして作成します。
- **リソース変更**: VMまたはコンテナのCPUコア数とメモリを変更します。
- **電源管理**: 起動、再起動、シャットダウン(ACPI)、強制停止を実行できます。
- **スナップショット管理**: スナップショットの作成、一覧表示、ロールバックが可能です。
- **動的監視設定**: Botを再起動せずに、コマンドで監視対象の追加・削除が可能です。
- **オートコンプリート**: コマンド入力時にVMIDのオートコンプリートが利用できます。
- **アクセス制御**: 特定のDiscordカテゴリ内でのみコマンドを使用できるように制限します。
- **非同期I/O**: 非同期API呼び出しにより、Botの応答性を最適化しています。

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
    # 監視対象のVMIDリスト (初期設定用)
    # 初回起動時にこのリストが 'monitor_list.json' に保存されます。
    # 以降の追加・削除はDiscordコマンド (/monitor) で行ってください。
    MONITOR_VM_IDS = [100, 101, 105]
    ```

## 使用方法

PythonでBotを起動します:

```bash
python bptcode.py
```

### コマンド

すべてのコマンドはスラッシュコマンド (`/`) です。VMID入力時にオートコンプリートが機能します。

#### 一般
- `/list`: すべてのVMおよびLXCコンテナの一覧とステータスを表示します。
- `/info <vmid>`: 詳細情報を表示し、操作ボタン（**起動**、**再起動**、**シャットダウン**）を提供します。
- `/create <template_id> <new_vmid> <name>`: テンプレートをクローンして新しいVMを作成します。
- `/resize <vmid> <cores> <memory_mb>`: CPUコア数とメモリ(MB)を変更します。変更は再起動後に適用されます。
- `/delete <vmid>`: リソースを削除します。**警告**: この操作は取り消せません。

#### 電源管理
- `/start <vmid>`: リソースを起動します。
- `/reboot <vmid>`: リソースを再起動します。
- `/shutdown <vmid>`: ACPIシャットダウン信号（安全な停止）を送信します。
- `/stop <vmid>`: リソースを強制停止（電源オフ）します。確認が必要です。

#### スナップショット管理
- `/snapshot create <vmid> <name>`: スナップショットを作成します。
- `/snapshot list <vmid>`: スナップショット一覧を表示します。
- `/snapshot rollback <vmid> <name>`: 特定のスナップショットにロールバックします（要確認）。

#### 監視設定
- `/monitor add <vmid>`: 監視リストにリソースを追加します。
- `/monitor remove <vmid>`: 監視リストからリソースを削除します。
- `/monitor list`: 現在監視しているリソースを表示します。

## 権限

このBotは `config.py` の `ALLOWED_CATEGORY_ID` で指定されたDiscordカテゴリ内でのみ使用できるように制限されています。指定されたカテゴリ内のチャンネルでコマンドを実行してください。

## 監視機能

Botは1分ごとにバックグラウンドタスクを実行し、監視対象リソースのステータスをチェックします。監視対象が停止している場合、`ALERT_CHANNEL_ID` にアラートが送信されます。監視リストは `monitor_list.json` に永続的に保存されます。
