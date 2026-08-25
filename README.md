# LeRobot-TM5-900

將 Techman Robot TM5-900 整合至 Hugging Face LeRobot，完成雙相機模仿學習的資料收集、ACT policy 訓練與真機推論。

> [!IMPORTANT]
> 由於完整專案包含的檔案與實驗資源過大，無法直接上傳至 GitHub。**本 GitHub repository 僅作為安裝與使用教學，不提供可直接安裝的完整程式碼。** 請務必從下方提供的 OneDrive 連結下載完整專案，再依本文件操作；只下載本 GitHub 教學內容無法執行 TM5-900。

本專案以 LeRobot `0.4.4` 為基礎，新增：

- TM5-900 的 LeRobot robot adapter（`tm_follower`）
- 終端機鍵盤遙操作器（`keyboard_xyz`）
- 適用 TM 手臂的資料收集與 policy 推論入口（`lerobot_record_tm.py`）
- 前、側雙相機資料錄製流程
- 在另一台 GPU 工作站透過 WSL 訓練 ACT，再將模型部署回控制端的完整流程

> [!WARNING]
> TM5-900 是工業協作型機械手臂。執行遙操作、資料收集或模型推論前，請確認急停、速度限制與碰撞保護皆可正常使用，清空工作範圍，並由熟悉設備的人員在旁監控。第一次測試請使用低速模式，且不要讓人員進入手臂可達範圍。模型輸出可能產生非預期動作，請勿在無人監控下執行。

## 目錄

- [模仿學習流程](#模仿學習流程)
- [系統架構](#系統架構)
- [專案結構與 TM5-900 整合方式](#專案結構與-tm5-900-整合方式)
- [安裝](#安裝)
- [啟動 TM ROS 2 Driver](#啟動-tm-ros-2-driver)
- [相機設定](#相機設定)
- [資料收集](#資料收集)
- [ACT 模型訓練](#act-模型訓練)
- [真機推論與評估](#真機推論與評估)
- [修改 state、action 或擴充其他手臂](#修改-stateaction-或擴充其他手臂)
- [常見問題](#常見問題)

## 模仿學習流程

模仿學習的目標，是讓模型從人類示範中學習「看到目前狀態後，下一步應該怎麼動」。本專案的流程分成三個階段：

```text
資料收集                         模型訓練                       真機推論
雙相機影像 + 關節狀態 + 動作  ->  ACT policy 學習示範軌跡  ->  影像/狀態輸入模型 -> TM5-900 動作
```

1. **資料收集**：操作員透過鍵盤控制 TM5-900。系統以固定 FPS 同步記錄前、側相機影像、六軸關節角度與夾爪狀態。
2. **模型訓練**：將資料集移到配備 NVIDIA GPU 的工作站，使用 ACT（Action Chunking with Transformers）進行訓練。
3. **真機推論**：將訓練完成的 checkpoint 搬回控制端。模型根據即時相機畫面與手臂狀態預測動作，再由 TM ROS 2 Driver 發送至真機。

若是第一次接觸 LeRobot，可先閱讀 [Seeed Studio 的 SO-ARM100／SO-ARM101 教學](https://wiki.seeedstudio.com/cn/lerobot_so100m/)。該教學使用小型手臂示範校正、遙操作、相機、資料集、訓練及評估；本專案沿用相同概念，但將硬體介面替換為 TM5-900、ROS 2 與 Robotiq 夾爪。

## 系統架構

```text
鍵盤 keyboard_xyz ── TCP 絕對位姿 ──┐
                                     v
雙相機 ───────────────────────> tm_follower <──> TM ROS 2 Driver <──> TM5-900
                                     │                  │
                                     │                  ├─ /tool_pose
                                     │                  ├─ /joint_states
                                     │                  └─ /send_script
                                     v
                    LeRobot Dataset（影像、j1~j6、gripper）
                                     │
                                     v
                              ACT policy 訓練
                                     │
                                     v
                             真機推論與評估資料
```

### State 與 action 定義

目前資料集與模型統一使用 7 維向量：

| 欄位           | 內容               | 單位／範圍                         |
| -------------- | ------------------ | ---------------------------------- |
| `j1`～`j6` | TM5-900 六軸關節角 | degree                             |
| `gripper`    | Robotiq 夾爪位置   | `150`～`255`（依目前程式設定） |

鍵盤遙操作的輸出則是另一套 7 維語意：`[x, y, z, rx, ry, rz, gripper]`。其中位置單位為 mm，旋轉單位為 degree。`tm_follower` 會以 `PTP("CPP", ...)` 執行 TCP 操作；資料錄製時，再以 `/joint_states` 回授寫入關節角 action。Policy 推論輸出關節角，則以 `PTP("JPP", ...)` 執行。

> 請勿只更改欄位名稱，卻沒有同步修改資料集 schema、robot adapter 與 teleoperator。向量維度相同不代表物理意義相同。

## 專案結構與 TM5-900 整合方式

```text
lerobot/
├── src/lerobot/robots/tm_follower/
│   ├── config_tm_follower.py       # robot type、ROS topic/service、相機設定
│   ├── robot_tm_follower.py        # ROS 2、TM Script、狀態、動作與夾爪介面
│   └── ROS2_gripper.py             # Robotiq 夾爪通訊
├── src/lerobot/teleoperators/keyboard_xyz/
│   ├── configuration_keyboard_xyz.py
│   └── teleop_keyboard_xyz.py      # 鍵盤控制與自動夾取／放置流程
├── src/lerobot/scripts/
│   └── lerobot_record_tm.py        # TM 專用錄製、續錄與 policy 推論入口
├── camera2.py                      # 雙相機預覽工具
└── command.txt                     # 常用指令備忘
```

### `tm_follower` 如何接入 LeRobot

`TMFollowerConfig` 以 `tm_follower` 名稱註冊至 `RobotConfig`；`TMFollower` 實作 LeRobot `Robot` 介面中的主要生命週期：

- `connect()`：建立 ROS 2 node、訂閱 `/tool_pose` 與 `/joint_states`、連接相機與夾爪。
- `get_observation()`：回傳六軸關節角、夾爪狀態及相機影像。
- `send_action()`：辨識 TCP 或 joint action，分別產生 TM Script 的 `CPP` 或 `JPP` 指令。
- `reset()`：將手臂與夾爪移回專案定義的 home pose。
- `disconnect()`：關閉相機、ROS thread 與 node。
- `observation_features`／`action_features`：宣告資料集與 policy 所看到的資料結構。

`lerobot_record_tm.py` 則負責把 robot observation 正規化為 LeRobot Dataset feature、同步寫入影像與 action、載入 policy，以及處理 episode 錄製流程。

## 安裝

### 需求

- 控制端：建議 Ubuntu 22.04、ROS 2 Humble、Python 3.10
- TM5-900 與可用的 TM ROS 2 Driver
- Robotiq 夾爪（目前預設 `/dev/ttyUSB0`、slave ID `9`）
- 兩台 UVC 相機
- `v4l2-ctl`、FFmpeg、Git 與 Conda／Miniforge
- 訓練端：Linux 或 WSL 2、NVIDIA GPU、相容的 NVIDIA Driver／CUDA／PyTorch

本專案曾以 RTX 3090 Ti 進行訓練，但 **LeRobot 並非只支援 RTX 40 系列**。是否能訓練取決於 PyTorch wheel 是否支援該 GPU 架構、NVIDIA Driver/CUDA 是否相容，以及模型與 batch 所需顯存。

### 1. 取得專案

完整專案只能從 [LeRobot-TM5-900 專案資料夾（OneDrive）](https://1drv.ms/u/c/94a944e4d17daff3/IQCnDA7EtmeAQaBqknIYeAb5AWwwsaFXQ6XNVmlwNqq4Uak?e=KosrZV) 下載。請在瀏覽器中開啟連結，選擇「下載」，並等待檔案完整下載。

以下假設下載的壓縮檔名稱為 `lerobot.zip`，且位於 `~/Downloads`。如果瀏覽器使用了不同檔名，請自行替換指令中的檔名。

```bash
# 安裝解壓縮工具
sudo apt update
sudo apt install -y unzip

# 建立專案放置位置
mkdir -p "$HOME/project_ws/src"

# 解壓縮從 OneDrive 下載的完整專案
unzip "$HOME/Downloads/lerobot.zip" -d "$HOME/project_ws/src"

# 確認解壓縮結果；應能找到專案根目錄的 pyproject.toml
find "$HOME/project_ws/src" -maxdepth 3 -type f -name pyproject.toml -print
```

若解壓縮後的資料夾名稱就是 `lerobot`，進入專案的指令為：

```bash
cd "$HOME/project_ws/src/lerobot"
ls -lah
test -f pyproject.toml && echo "找到 LeRobot 專案根目錄"
```

如果壓縮檔解開後還有一層資料夾，請進入前一步 `find` 所顯示、包含專案根目錄 `pyproject.toml` 的目錄。後續的 `python -m pip install -e .` 必須在該目錄執行。

### 2. 安裝完整專案

先建立 Python 3.10 Conda 環境及系統工具：

```bash
conda create -y -n lerobot python=3.10
conda activate lerobot
conda install -y ffmpeg=7.1.1 -c conda-forge

sudo apt update
sudo apt install -y v4l-utils rsync build-essential unzip

python -m pip install --upgrade pip
```

接著進入剛才從雲端解壓縮的專案根目錄，以 editable mode 安裝完整專案及其 Python 相依套件：

```bash
cd "$HOME/project_ws/src/lerobot"
python -m pip install -e .
```

安裝成功後，無論從哪個工作目錄執行 Python，都會載入這個資料夾內的 LeRobot 程式；修改原始碼後通常不需要重新複製或重新安裝。

由於 `rclpy` 與 `tm_msgs` 來自 ROS 2／TM Driver workspace，而非一般 PyPI 套件，每次開啟新終端機時還需要載入 ROS 環境：

```bash
source /opt/ros/humble/setup.bash
source <TM_ROS2_WORKSPACE>/install/setup.bash
conda activate lerobot
cd "$HOME/project_ws/src/lerobot"
```

若 Conda 中的 Python 無法載入系統 ROS 2 Python 套件，請確認 Python 版本與 ROS 2 Humble 相容，並檢查 `PYTHONPATH`。不要用來源不明的 `pip install rclpy` 取代完整 ROS 2 安裝。

### 3. 驗證專案安裝

```bash
python -c "import lerobot; print('LeRobot import OK')"
python -c "import rclpy; from tm_msgs.srv import SendScript; print('ROS 2 / tm_msgs import OK')"
python -m pip show lerobot
which ffmpeg
v4l2-ctl --version
```

`python -m pip show lerobot` 的 `Editable project location` 應指向剛才解壓縮的 `$HOME/project_ws/src/lerobot`。若不是，代表目前環境載入了其他 LeRobot 版本，請先移除衝突版本，再回到專案根目錄重新執行 `python -m pip install -e .`。

## 啟動 TM ROS 2 Driver

先在 TMflow 完成外部控制所需的網路、Listen Node／Ethernet Slave 與安全設定，再啟動對應版本的官方 TM Driver。官方 driver 會發布 `/joint_states`、`/tool_pose`，並提供 SendScript service；請參考 [Techman Robot 官方 ROS 2 repository](https://github.com/TechmanRobotInc/tmr_ros2/tree/humble)。

```bash
source /opt/ros/humble/setup.bash
source <TM_ROS2_WORKSPACE>/install/setup.bash

ros2 run tm_driver tm_driver robot_ip:=192.168.250.40
```

請將 IP 改成實際機器人位址。另一個終端機可用以下指令檢查連線：

```bash
ros2 topic echo /joint_states --once
ros2 topic echo /tool_pose --once
ros2 service list | grep send_script
```

本專案預設 service 為 `/send_script`。若 `ros2 service list` 顯示 `/tm_driver/send_script`，啟動錄製時加入：

```bash
--robot.send_script_service=/tm_driver/send_script
```

## 相機設定

### 1. 查詢裝置編號

```bash
v4l2-ctl --list-devices
```

請記錄前視與側視相機對應的 `/dev/video*`。重新插拔 USB 或重新開機後編號可能改變；正式實驗建議建立固定的 udev symlink，避免裝置順序變動。

### 2. 預覽雙相機(路經需照實際電腦做修改)

先修改 `camera2.py` 中的 `CAM0_INDEX` 與 `CAM8_INDEX`，再執行：

```bash
PYTHONNOUSERSITE=1 \
/home/omda/miniconda3/envs/lerobot/bin/python \
/home/omda/project_ws/src/lerobot/camera2.py
```

確認畫面方向、工作區覆蓋範圍、曝光與遮擋情形後，按 `q` 關閉預覽。

> `camera2.py` 使用的是 OpenCV 整數 index；錄製指令使用 `/dev/video*` 路徑。兩者應實際測試，不要只依名稱猜測對應關係。

### 3. 鎖定格式與 FPS

以下以 `/dev/video6` 與 `/dev/video8` 為例：

```bash
v4l2-ctl -d /dev/video6 --set-fmt-video=width=1280,height=720,pixelformat=MJPG
v4l2-ctl -d /dev/video6 --set-parm=10

v4l2-ctl -d /dev/video8 --set-fmt-video=width=1280,height=720,pixelformat=MJPG
v4l2-ctl -d /dev/video8 --set-parm=10
```

驗證實際設定：

```bash
v4l2-ctl -d /dev/video6 --get-fmt-video
v4l2-ctl -d /dev/video6 --get-parm
v4l2-ctl -d /dev/video8 --get-fmt-video
v4l2-ctl -d /dev/video8 --get-parm
```

資料收集與推論必須使用相同的相機角色名稱（`front`、`side`）、影像尺寸、色彩格式與 FPS；視角及機器人工作區也應盡量一致。

## 資料收集

### 1. 開啟控制環境

建議至少準備兩個終端機：第一個執行 TM Driver，第二個執行 LeRobot。

```bash
source /opt/ros/humble/setup.bash
source <TM_ROS2_WORKSPACE>/install/setup.bash
conda activate lerobot
cd "$HOME/project_ws/src/lerobot"
```

### 2. 鍵盤控制

`keyboard_xyz` 預設每次平移 `5 mm`、旋轉 `2.5°`。按鍵如下：

| 按鍵         | 功能                                                        |
| ------------ | ----------------------------------------------------------- |
| `W`／`S` | TCP`x` 增加／減少                                         |
| `A`／`D` | TCP`y` 增加／減少                                         |
| `R`／`F` | TCP`z` 增加／減少                                         |
| `I`／`K` | `rx` 增加／減少                                           |
| `O`／`L` | `ry` 增加／減少                                           |
| `P`／`;` | `rz` 增加／減少                                           |
| `]`／`[` | 夾爪關閉／開啟（每次 5）                                    |
| `Space`    | 啟動自動關爪流程，最長持續 9 秒                             |
| `Z`        | 執行專案內設定的 joint 中繼點、放置、開爪及回 home 自動流程 |
| `Q`        | 中止 keyboard teleoperator                                  |

可用 CLI 調整平移與旋轉步距，例如：

```bash
--teleop.pos_step=2.0 --teleop.rot_step=1.0
```

> `Z` 的 joint waypoints、home pose、夾爪範圍與自動流程是依目前實驗設計寫在 `teleop_keyboard_xyz.py` 中，不是所有任務都通用。換治具、換工作台或換手臂後，必須先重新確認每一個 waypoint。

### 3. 建立新資料集

確認 `$DATASET_ROOT` 不含要保留的資料。以下指令會建立 15 個 episode：

```bash
DATASET_ROOT="$HOME/tm_lerobot_datasets"
DATASET_ID="local/tm_2cam_test"

# 只有確定要從零開始時才取消下一行註解；此操作會刪除整個資料集。
# rm -rf "$DATASET_ROOT"

/home/omda/miniconda3/envs/lerobot/bin/python -m lerobot.scripts.lerobot_record_tm \
  --robot.type=tm_follower \
  --teleop.type=keyboard_xyz \
  --robot.cameras="{ front: {type: opencv, index_or_path: /dev/video6, width: 1280, height: 720, fps: 10, fourcc: \"MJPG\", warmup_s: 5}, side: {type: opencv, index_or_path: /dev/video8, width: 1280, height: 720, fps: 10, fourcc: \"MJPG\", warmup_s: 5}}" \
  --display_data=false \
  --dataset.repo_id="$DATASET_ID" \
  --dataset.num_episodes=15 \
  --dataset.single_task="TM test move" \
  --dataset.root="$DATASET_ROOT" \
  --dataset.push_to_hub=false \
  --dataset.fps=10 \
  --dataset.episode_time_s=600 \
  --dataset.reset_time_s=5
```

主要參數：

| 參數                         | 說明                                                            |
| ---------------------------- | --------------------------------------------------------------- |
| `--robot.type`             | 使用本專案註冊的`tm_follower`                                 |
| `--teleop.type`            | 使用終端機`keyboard_xyz` 控制器                               |
| `--robot.cameras`          | 相機名稱、裝置、解析度、FPS、編碼及暖機秒數                     |
| `--display_data`           | 是否啟用 Rerun 即時視覺化；關閉可減少額外負載                   |
| `--dataset.repo_id`        | LeRobot 資料集識別名稱；本機資料仍需符合`namespace/name` 格式 |
| `--dataset.num_episodes`   | 本次要完成的 episode 數量                                       |
| `--dataset.single_task`    | 每一筆資料附帶的任務文字，訓練與推論應一致                      |
| `--dataset.root`           | 資料實際寫入位置                                                |
| `--dataset.push_to_hub`    | `false` 表示不自動上傳 Hugging Face Hub                       |
| `--dataset.fps`            | 控制與記錄頻率；需與相機及續錄設定一致                          |
| `--dataset.episode_time_s` | 單一 episode 最長錄製時間                                       |
| `--dataset.reset_time_s`   | episode 間整理場景的時間                                        |

錄製階段的全域快捷鍵：

| 按鍵            | 功能                                                                           |
| --------------- | ------------------------------------------------------------------------------ |
| `→` 右方向鍵 | 提前結束目前 episode，儲存後進入下一個                                         |
| `←` 左方向鍵 | 取消目前 episode，重新錄製同一個 episode                                       |
| `Esc`         | 立即停止整個錄製工作，完成影片編碼與資料集 finalize；若有開啟 Hub 上傳才會上傳 |

建議每個 episode 都保持任務目標、起始擺放、相機位置與示範節奏一致，但仍保留適量物件位置變化，避免模型只記住單一路徑。錄完一個批次後，先備份整個 dataset 再續錄。

### 4. 續錄既有資料集

```bash
DATASET_ROOT="$HOME/tm_lerobot_datasets"
DATASET_ID="local/tm_2cam_test"

/home/omda/miniconda3/envs/lerobot/bin/python -m lerobot.scripts.lerobot_record_tm \
  --robot.type=tm_follower \
  --teleop.type=keyboard_xyz \
  --robot.cameras="{ front: {type: opencv, index_or_path: /dev/video6, width: 1280, height: 720, fps: 10, fourcc: \"MJPG\", warmup_s: 5}, side: {type: opencv, index_or_path: /dev/video8, width: 1280, height: 720, fps: 10, fourcc: \"MJPG\", warmup_s: 5}}" \
  --display_data=false \
  --dataset.repo_id="$DATASET_ID" \
  --dataset.num_episodes=7 \
  --dataset.single_task="TM test move" \
  --dataset.root="$DATASET_ROOT" \
  --dataset.push_to_hub=false \
  --dataset.fps=10 \
  --dataset.episode_time_s=600 \
  --dataset.reset_time_s=5 \
  --resume=true
```

這裡的 `num_episodes=7` 表示本次再錄 7 個，不是總數改成 7。續錄時必須維持相同的 feature schema、相機名稱、解析度、FPS、`repo_id` 與資料根目錄，否則 compatibility check 可能失敗，或產生無法用於同一模型的資料。

## ACT 模型訓練

以下示範將控制端錄好的資料移到 Windows 桌面，再由配備 RTX 3090 Ti 的 WSL 工作站訓練。

### 1. 準備 WSL 訓練環境

在 Windows 安裝 WSL 2、Ubuntu、NVIDIA Driver 與 Conda，並依[安裝章節](#安裝)建立相同版本的 LeRobot 環境。先驗證 CUDA：

```bash
conda activate lerobot
python -c "import torch; print(torch.__version__); print(torch.cuda.is_available()); print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CUDA unavailable')"
nvidia-smi
```

### 2. 將資料複製到 WSL

```bash
SRC="/mnt/c/Users/Administrator/Desktop/tm_lerobot_datasets"
DST="$HOME/datasets/tm_lerobot_datasets"

mkdir -p "$DST"
rsync -ah --delete --info=progress2 "$SRC"/ "$DST"/
```

> `--delete` 會刪除目的端中、來源端不存在的檔案。執行前請再次確認 `SRC` 與 `DST`，不要把方向寫反。

確認 metadata 已成功複製：

```bash
ls -lah "$HOME/datasets/tm_lerobot_datasets/meta/info.json"
ls -lah "$HOME/datasets/tm_lerobot_datasets/meta/stats.json"
```

### 3. 開始訓練

```bash
conda activate lerobot
cd "$HOME/project_ws/src/lerobot"

lerobot-train \
  --dataset.root="$HOME/datasets/tm_lerobot_datasets" \
  --dataset.repo_id="local/tm_lerobot_datasets" \
  --policy.type=act \
  --policy.repo_id="local/act_tm_lerobot_datasets" \
  --policy.device=cuda \
  --policy.use_amp=true \
  --policy.push_to_hub=false \
  --policy.chunk_size=200 \
  --policy.n_action_steps=200 \
  --output_dir="$HOME/lerobot_outputs/train/act_tm_lerobot_datasets_$(date +%Y%m%d_%H%M%S)" \
  --job_name="act_tm_lerobot_datasets" \
  --wandb.enable=true \
  --wandb.disable_artifact=true \
  --steps=140000 \
  --save_freq=20000
```

| 參數                       | 說明                                                     |
| -------------------------- | -------------------------------------------------------- |
| `dataset.root`           | 包含`meta/`、`data/`、`videos/` 的本機資料集根目錄 |
| `dataset.repo_id`        | 訓練時使用的資料集邏輯名稱                               |
| `policy.type=act`        | 使用 ACT policy                                          |
| `policy.repo_id`         | 模型邏輯名稱；只有啟用 Hub 上傳時才會推送                |
| `policy.device=cuda`     | 使用 NVIDIA GPU                                          |
| `policy.use_amp=true`    | 啟用 automatic mixed precision，通常可降低顯存與加速訓練 |
| `chunk_size`             | 模型一次預測的 action 序列長度                           |
| `n_action_steps`         | 每次推論實際執行的 action step 數                        |
| `output_dir`             | log、設定與 checkpoint 輸出位置；時間戳可避免覆蓋舊實驗  |
| `wandb.enable`           | 將 loss 等指標記錄到 Weights & Biases；第一次使用需登入  |
| `wandb.disable_artifact` | 不將大型 artifact 上傳到 W&B                             |
| `steps`                  | optimizer 更新總步數                                     |
| `save_freq`              | 每隔多少 step 儲存 checkpoint                            |

`chunk_size=200`、`n_action_steps=200` 與 `steps=140000` 是本實驗的起始設定，不保證適合所有任務。10 FPS 下 200 steps 約對應 20 秒動作區段；若任務需要頻繁根據新影像修正，可測試較短 action horizon。請比較 validation loss 與真機成功率，不要只選最後一個 checkpoint。

### 4. 將模型複製回 Windows(路經需照實際電腦做修改)

依終端機實際輸出修改時間戳：

```bash
OUT="/home/juze/lerobot_outputs/train/act_tm_lerobot_datasets_20260704_113746"
WIN_DST="/mnt/c/Users/Administrator/Desktop/act_tm_lerobot_datasets_20260704_113746"

mkdir -p "$WIN_DST"
rsync -ah --info=progress2 "$OUT"/ "$WIN_DST"/
sync

du -sh "$OUT" "$WIN_DST"
ls -lah "$WIN_DST"
```

確認檔案大小與 checkpoint 內容完整後，再將整個模型資料夾移到控制 TM5-900 的機台。

## 真機推論與評估

### 1. 啟動與檢查

1. 啟動 TM ROS 2 Driver，確認 `/joint_states`、`/tool_pose` 與 SendScript service。
2. 啟用 `lerobot` Conda 環境並進入專案。
3. 依[相機設定](#相機設定)重新確認前、側相機裝置。
4. 確保相機名稱、順序、解析度、FPS、場景視角及 task text 與訓練時一致。
5. 先將 TMflow 速度設低，確認急停可立即介入。

### 2. 執行 ACT policy(路經需照實際電腦做修改)

```bash
source /opt/ros/humble/setup.bash
source <TM_ROS2_WORKSPACE>/install/setup.bash
conda activate lerobot
cd "$HOME/project_ws/src/lerobot"

POLICY_DIR="/home/juze/lerobot/act_tm_lerobot_datasets_20260621_135115/checkpoints/100000/pretrained_model"
DATASET_ROOT="$HOME/tm_lerobot_eval"
DATASET_ID="local/eval_tm_2cam_act"

python -m lerobot.scripts.lerobot_record_tm \
  --robot.type=tm_follower \
  --robot.cameras="{ front: {type: opencv, index_or_path: /dev/video6, width: 1280, height: 720, fps: 10, fourcc: \"MJPG\", warmup_s: 5}, side: {type: opencv, index_or_path: /dev/video8, width: 1280, height: 720, fps: 10, fourcc: \"MJPG\", warmup_s: 5}}" \
  --display_data=false \
  --dataset.repo_id="$DATASET_ID" \
  --dataset.num_episodes=5 \
  --dataset.single_task="TM test move" \
  --dataset.root="$DATASET_ROOT" \
  --dataset.push_to_hub=false \
  --dataset.fps=10 \
  --dataset.episode_time_s=600 \
  --dataset.reset_time_s=15 \
  --policy.type=act \
  --policy.pretrained_path="$POLICY_DIR" \
  --policy.device=cuda \
  --policy.use_amp=true
```

推論時不需要 `--teleop.type=keyboard_xyz`；動作由 ACT policy 產生。主要 policy 參數如下：

- `policy.pretrained_path`：checkpoint 中的 `pretrained_model` 目錄。
- `policy.device`：執行推論的裝置；無相容 GPU 時可測試 `cpu`，但即時性可能不足。
- `policy.use_amp`：在 CUDA 上使用 mixed precision。
- `dataset.*`：推論過程仍會錄成新的 evaluation dataset，方便事後分析失敗案例或整理成新訓練資料。

### 3. 計算成功率

`lerobot_record_tm.py` 會輸出評估 episode，但不會自動判定任務成功。

## 修改 state、action 或擴充其他手臂

### 修改 TM5-900 的 state/action

目前的 dataset schema 是 `[j1, j2, j3, j4, j5, j6, gripper]`。若要加入力矩、速度、額外 IO 或改成 TCP state，至少要同步檢查：

1. `src/lerobot/robots/tm_follower/robot_tm_follower.py`
   - 修改名稱常數與 feature shape。
   - 在 ROS callback 中保存新的 sensor state。
   - 更新 `observation_features`、`action_features`、`get_observation()`、action parser 與 `send_action()`。
   - 清楚定義每個欄位的單位、範圍與絕對／相對控制語意。
2. `src/lerobot/scripts/lerobot_record_tm.py`
   - 更新 state/action 名稱、dataset feature 建立、normalization 與 action extraction。
   - 確保 policy 輸入輸出和送入 robot 的欄位順序一致。
3. `src/lerobot/teleoperators/keyboard_xyz/`
   - 若 teleoperator 也改變輸出，更新 `action_features`、`get_action()` 與設定 dataclass。
4. 測試與資料
   - 新增 shape、dtype、單位、邊界值與真機 dry-run 測試。
   - schema 改變後建立新資料集並重新訓練；既有 checkpoint 不會自動理解新增或重排後的欄位。

建議在實際移動前先列印一筆 observation/action，逐欄確認名稱、順序、單位與數值範圍，再以低速、小位移測試。

### 擴充其他類型手臂

若要新增例如 `my_arm_follower`：

1. 在 `src/lerobot/robots/my_arm_follower/` 建立 config 與 robot class。
2. 使用 `@RobotConfig.register_subclass("my_arm_follower")` 註冊 type。
3. 實作 `connect`、`disconnect`、`get_observation`、`send_action`、`observation_features`、`action_features` 等介面。
4. 在 package 的 `__init__.py` 匯出 config 與 class，並確認 LeRobot 的 robot factory 能載入。
5. 若需要新的輸入裝置，在 `src/lerobot/teleoperators/` 以相同方式註冊 `TeleoperatorConfig` 並實作 teleoperator。
6. 若資料語意與 TM 專用 recorder 不同，優先使用通用 `lerobot-record`，或建立獨立 recorder；不要在 TM 專用分支堆疊不相容的特例。
7. 先用 mock／模擬器驗證 feature 與 action，再接上真機低速測試。

## 常見問題

### 找不到 `tm_msgs.srv.SendScript`

TM ROS 2 workspace 尚未 build／source，或目前 Conda Python 看不到 ROS 2 site-packages。重新執行：

```bash
source /opt/ros/humble/setup.bash
source <TM_ROS2_WORKSPACE>/install/setup.bash
python -c "from tm_msgs.srv import SendScript"
```

### 等不到 SendScript service

```bash
ros2 service list | grep send_script
```

確認 TMflow Listen Node、robot IP、driver 連線與 service 完整名稱。如果 service 是 `/tm_driver/send_script`，使用 `--robot.send_script_service=/tm_driver/send_script`。

### 相機無法開啟或 FPS 不正確

先停止其他占用相機的程式，再用 `v4l2-ctl --list-devices`、`--get-fmt-video` 與 `--get-parm` 檢查。USB 頻寬不足時，請使用 MJPG、分散到不同 USB controller，或降低解析度／FPS；但更改後必須重新建立一致的訓練與推論設定。

### `--resume=true` 出現 dataset compatibility error

檢查 `dataset.root`、`repo_id`、FPS、camera key、影像尺寸以及 state/action schema 是否與第一批資料完全相同。若 schema 已改動，請建立新資料集，不要強行續錄。

### CUDA out of memory

先關閉其他 GPU 程式並確認 `nvidia-smi`。接著可降低 ACT 設定或訓練 batch size（依目前版本可用的 CLI config 為準），保留 AMP，並重新比較模型品質。不要把 `chunk_size` 與 `n_action_steps` 當成單純的顯存開關；兩者也會改變 policy 的時間行為。

### 真機推論動作異常

立即停止並檢查：相機 `front/side` 是否對調、視角是否改變、state/action 順序與單位、checkpoint 的 dataset stats、task text、FPS、home pose、夾爪範圍及 TM Driver 回授。不要在未找出原因前直接提高速度重試。

## 參考資料

- [Hugging Face LeRobot](https://github.com/huggingface/lerobot)
- [LeRobot 文件](https://huggingface.co/docs/lerobot/index)
- [Seeed Studio：SO-ARM100／SO-ARM101 LeRobot 教學](https://wiki.seeedstudio.com/cn/lerobot_so100m/)
- [Techman Robot 官方 ROS 2 Driver](https://github.com/TechmanRobotInc/tmr_ros2/tree/humble)
