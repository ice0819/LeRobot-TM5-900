


# import sys
# import select
# import termios
# import tty
# import time
# import numpy as np

# from lerobot.teleoperators.teleoperator import Teleoperator
# from .configuration_keyboard_xyz import KeyboardXYZTeleopConfig


# STATE_NAMES = ["x", "y", "z", "rx", "ry", "rz", "gripper"]


# class KeyboardXYZTeleop(Teleoperator):
#     config_class = KeyboardXYZTeleopConfig
#     name = "keyboard_xyz"

#     def __init__(self, config: KeyboardXYZTeleopConfig):
#         super().__init__(config)
#         self.config = config
#         self.pos_step = float(config.pos_step)
#         self.rot_step = float(config.rot_step)

#         self._is_connected = False
#         self._is_calibrated = True
#         self._old_term_settings = None

#         # ===== control frequency =====
#         self._min_action_interval = 0.1
#         self._last_action_time = 0.0

#         # ===== gripper settings =====
#         self._gripper_step = 20.0
#         self._gripper_cmd_interval = 0.1
#         self._gripper_open_pos = 150.0
#         self._gripper_close_pos_max = 255.0

#         # ===== default / home absolute target pose =====
#         self._home_target_pose = np.array(
#             [-250.0, -500.0, 150.0, -180.0, 0.0, 0.0, self._gripper_open_pos],
#             dtype=np.float32,
#         )
#         self._target_pose = self._home_target_pose.copy()

#         # ===== Z key auto flow target poses =====
#         # 按下 z 後，不再直接跳到放置點，而是：
#         # current -> 中間點 -> 放置點，兩段都用 0.1 s 線性內插。
#         # 第 7 個 gripper 在移動過程中維持關爪 255，到了放置點後才放開。
#         self._z_mid_pose = np.array(
#             [-200.0, -670.0, 200.0, 180.0, 0.0, 0.0, self._gripper_close_pos_max],
#             dtype=np.float32,
#         )
#         self._z_target_pose = np.array(
#             [-200.0, -670.0, 100.0, 180.0, 0.0, 0.0, self._gripper_close_pos_max],
#             dtype=np.float32,
#         )

#         # 每 0.1 s 發送一個內插點。
#         # 內插點數由距離自動決定：每一步最大平移量約等於 pos_step。
#         self._z_interp_dt_s = 0.1
#         self._z_interp_pos_step_mm = max(abs(float(self.pos_step)), 5.0)

#         # ===== SPACE auto close only =====
#         # SPACE 現在只做自動關爪，不再有「第二次空白鍵開爪回 HOME」機制。
#         self._auto_closing = False
#         self._auto_close_start_time = 0.0
#         self._auto_close_timeout_s = 9.0
#         self._last_gripper_auto_time = 0.0

#         # ===== z key auto flow =====
#         # z 流程：
#         # current -> 內插到中間點 -> 內插到放置點 -> 等待 1 s -> 開爪
#         # -> 等待 1 s -> 8 個固定 waypoint 回中間點與 HOME
#         self._z_flow_active = False
#         self._z_flow_opened = False
#         self._z_returning_home = False
#         self._z_flow_start_time = 0.0
#         self._z_open_start_time = 0.0
#         self._z_return_home_start_time = 0.0
#         self._z_open_delay_s = 1.0
#         self._z_return_home_delay_s = 1.0

#         self._z_waypoints = []
#         self._z_waypoint_index = 0
#         self._z_last_waypoint_time = 0.0

#         # feedback 保留，目前不拿來停止流程
#         self._feedback = {}

#     @property
#     def action_features(self):
#         return {
#             "action": {
#                 "dtype": "float32",
#                 "shape": (7,),
#                 "names": STATE_NAMES,
#             }
#         }

#     @property
#     def feedback_features(self):
#         return {}

#     @property
#     def is_connected(self):
#         return self._is_connected

#     @property
#     def is_calibrated(self):
#         return self._is_calibrated

#     def configure(self):
#         return

#     def calibrate(self):
#         self._is_calibrated = True

#     def connect(self):
#         if self._is_connected:
#             return

#         self._old_term_settings = termios.tcgetattr(sys.stdin)
#         tty.setcbreak(sys.stdin.fileno())
#         self._is_connected = True

#         print("[KeyboardXYZTeleop] connected")
#         print(
#             "keys: w/s=x, d/a=y, r/f=z, "
#             "i/k=rx, o/l=ry, p/;=rz, "
#             "]/[]=manual gripper, SPACE=auto close, z=target/open/home flow, q=quit"
#         )
#         print("[KeyboardXYZTeleop] SPACE flow:")
#         print("  SPACE: auto close only")
#         print("[KeyboardXYZTeleop] z flow:")
#         print("  z: interpolate to midpoint -> interpolate to place -> wait 1s -> open gripper -> 8-point return through midpoint -> HOME")

#     def disconnect(self):
#         if self._old_term_settings is not None:
#             termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self._old_term_settings)
#             self._old_term_settings = None

#         self._is_connected = False
#         print("[KeyboardXYZTeleop] disconnected")

#     def reset_for_new_episode(self):
#         self._target_pose = self._home_target_pose.copy()

#         self._auto_closing = False
#         self._last_action_time = 0.0
#         self._last_gripper_auto_time = 0.0
#         self._auto_close_start_time = 0.0

#         self._z_flow_active = False
#         self._z_flow_opened = False
#         self._z_returning_home = False
#         self._z_flow_start_time = 0.0
#         self._z_open_start_time = 0.0
#         self._z_return_home_start_time = 0.0
#         self._z_waypoints = []
#         self._z_waypoint_index = 0
#         self._z_last_waypoint_time = 0.0

#         self._feedback = {}

#         print(f"[KeyboardXYZTeleop] reset_for_new_episode -> target={self._target_pose.tolist()}")

#     def set_home_target_pose(self, pose7):
#         arr = np.asarray(pose7, dtype=np.float32).reshape(7)
#         self._home_target_pose = arr.copy()
#         print(f"[KeyboardXYZTeleop] set_home_target_pose -> {self._home_target_pose.tolist()}")

#     def set_z_mid_pose(self, pose7):
#         arr = np.asarray(pose7, dtype=np.float32).reshape(7)
#         self._z_mid_pose = arr.copy()
#         print(f"[KeyboardXYZTeleop] set_z_mid_pose -> {self._z_mid_pose.tolist()}")

#     def set_z_target_pose(self, pose7):
#         arr = np.asarray(pose7, dtype=np.float32).reshape(7)
#         self._z_target_pose = arr.copy()
#         print(f"[KeyboardXYZTeleop] set_z_target_pose -> {self._z_target_pose.tolist()}")

#     def _make_linear_waypoints(self, start_pose, end_pose):
#         """
#         產生 start_pose -> end_pose 的線性內插點。
#         - 平移 xyz：依照 pos_step 自動決定點數。
#         - 旋轉 rx ry rz：使用最短角度差，避免 -180 到 180 被插成 360 度大旋轉。
#         - 回傳不包含 start_pose，只包含後續要送出的 waypoint。
#         """
#         start = np.asarray(start_pose, dtype=np.float32).reshape(7)
#         end = np.asarray(end_pose, dtype=np.float32).reshape(7)

#         pos_delta = end[:3] - start[:3]

#         # Euler 角使用最短角度差，單位為 degree。
#         rot_delta = (end[3:6] - start[3:6] + 180.0) % 360.0 - 180.0

#         max_pos_delta = float(np.max(np.abs(pos_delta)))
#         max_rot_delta = float(np.max(np.abs(rot_delta)))

#         pos_step = max(float(self._z_interp_pos_step_mm), 1e-6)
#         rot_step = max(abs(float(self.rot_step)), 1e-6)

#         n_pos = int(np.ceil(max_pos_delta / pos_step))
#         n_rot = int(np.ceil(max_rot_delta / rot_step))
#         n_steps = max(1, n_pos, n_rot)

#         waypoints = []
#         for i in range(1, n_steps + 1):
#             alpha = i / n_steps
#             pose = start.copy()
#             pose[:3] = start[:3] + alpha * pos_delta
#             pose[3:6] = start[3:6] + alpha * rot_delta
#             pose[6] = end[6]
#             waypoints.append(pose.astype(np.float32))

#         return waypoints

#     def _make_fixed_linear_waypoints(self, start_pose, end_pose, n_steps: int):
#         """
#         產生固定數量的線性內插點。
#         - 回程使用：放置點 -> 中間點 2 點，中間點 -> HOME 2 點，總共 8 點。
#         - 回傳不包含 start_pose，包含 end_pose。
#         """
#         start = np.asarray(start_pose, dtype=np.float32).reshape(7)
#         end = np.asarray(end_pose, dtype=np.float32).reshape(7)

#         n_steps = max(1, int(n_steps))

#         pos_delta = end[:3] - start[:3]
#         rot_delta = (end[3:6] - start[3:6] + 180.0) % 360.0 - 180.0

#         waypoints = []
#         for i in range(1, n_steps + 1):
#             alpha = i / n_steps
#             pose = start.copy()
#             pose[:3] = start[:3] + alpha * pos_delta
#             pose[3:6] = start[3:6] + alpha * rot_delta
#             pose[6] = end[6]
#             waypoints.append(pose.astype(np.float32))

#         return waypoints

#     def _read_key_nonblocking(self):
#         dr, _, _ = select.select([sys.stdin], [], [], 0.0)
#         if not dr:
#             return None

#         chars = []
#         while True:
#             dr, _, _ = select.select([sys.stdin], [], [], 0.0)
#             if not dr:
#                 break

#             ch = sys.stdin.read(1)
#             if not ch:
#                 break

#             chars.append(ch)

#         if not chars:
#             return None

#         return chars[-1]

#     def _current_gripper_pos_from_feedback(self):
#         if isinstance(self._feedback, dict):
#             for key in ("gripper_pos", "gripper_position", "gripper", "gripper.pos"):
#                 if key in self._feedback:
#                     try:
#                         return float(self._feedback[key])
#                     except Exception:
#                         return None
#         return None

#     def _start_space_auto_close(self):
#         # SPACE：只做自動關爪，不再切換到開爪回 HOME。
#         self._auto_closing = True
#         self._z_flow_active = False
#         self._z_flow_opened = False

#         self._auto_close_start_time = time.perf_counter()
#         self._last_gripper_auto_time = 0.0

#         print("[KeyboardXYZTeleop] AUTO CLOSE START (9s chase to 255)")

#     def _start_z_auto_flow(self, now: float):
#         # z：從目前 target_pose 開始，先內插到中間點，再內插到放置點。
#         self._auto_closing = False

#         start_pose = self._target_pose.copy()
#         start_pose[6] = self._gripper_close_pos_max

#         mid_pose = self._z_mid_pose.copy()
#         mid_pose[6] = self._gripper_close_pos_max

#         place_pose = self._z_target_pose.copy()
#         place_pose[6] = self._gripper_close_pos_max

#         # 兩段路徑：
#         # 1. current -> midpoint
#         # 2. midpoint -> place
#         self._z_waypoints = []
#         self._z_waypoints.extend(self._make_linear_waypoints(start_pose, mid_pose))
#         self._z_waypoints.extend(self._make_linear_waypoints(mid_pose, place_pose))

#         self._target_pose = start_pose.copy()
#         self._z_waypoint_index = 0
#         self._z_last_waypoint_time = now - self._z_interp_dt_s  # 讓第一個點可以立即送出

#         self._z_flow_active = True
#         self._z_flow_opened = False
#         self._z_returning_home = False
#         self._z_flow_start_time = now
#         self._z_open_start_time = 0.0
#         self._z_return_home_start_time = 0.0

#         print("[KeyboardXYZTeleop] Z FLOW START")
#         print(f"  start={start_pose.tolist()}")
#         print(f"  mid={mid_pose.tolist()}")
#         print(f"  place={place_pose.tolist()}")
#         print(f"  waypoints={len(self._z_waypoints)}, dt={self._z_interp_dt_s}s")

#     def _auto_gripper_update(self, now: float):
#         if not self._auto_closing:
#             return

#         if (now - self._auto_close_start_time) > self._auto_close_timeout_s:
#             self._auto_closing = False
#             print("[KeyboardXYZTeleop] AUTO CLOSE STOP by timeout (9s)")
#             return

#         if (now - self._last_gripper_auto_time) < self._gripper_cmd_interval:
#             return

#         self._target_pose[6] = self._gripper_close_pos_max
#         self._last_gripper_auto_time = now

#     def _z_auto_flow_update(self, now: float):
#         if not self._z_flow_active:
#             return

#         # 1) 每 0.1 s 送出下一個內插 waypoint。
#         # outward waypoints 的 gripper = 255；return waypoints 的 gripper = 150。
#         if self._z_waypoint_index < len(self._z_waypoints):
#             if (now - self._z_last_waypoint_time) < self._z_interp_dt_s:
#                 return

#             self._target_pose = self._z_waypoints[self._z_waypoint_index].copy()

#             self._z_waypoint_index += 1
#             self._z_last_waypoint_time = now

#             if self._z_waypoint_index == len(self._z_waypoints):
#                 if self._z_returning_home:
#                     # 回程 waypoint 全部送完，流程結束。
#                     self._target_pose = self._home_target_pose.copy()
#                     self._target_pose[6] = self._gripper_open_pos

#                     self._z_flow_active = False
#                     self._z_flow_opened = False
#                     self._z_returning_home = False
#                     self._z_waypoints = []
#                     self._z_waypoint_index = 0
#                     print("[KeyboardXYZTeleop] Z FLOW RETURN HOME DONE")
#                 else:
#                     # 放置路徑送完，開始等待開爪。
#                     self._z_open_start_time = now
#                     print("[KeyboardXYZTeleop] Z FLOW REACHED PLACE, wait 1s then open gripper")
#             return

#         # 2) 到放置點後，等待 1 s 再開爪。
#         if not self._z_flow_opened:
#             if self._z_open_start_time <= 0.0:
#                 self._z_open_start_time = now
#                 return

#             if (now - self._z_open_start_time) < self._z_open_delay_s:
#                 return

#             self._target_pose[6] = self._gripper_open_pos
#             self._z_flow_opened = True
#             self._z_return_home_start_time = now
#             print("[KeyboardXYZTeleop] Z FLOW OPEN GRIPPER")
#             return

#         # 3) 開爪後等待 1 s，再產生「放置點 -> 中間點 -> HOME」的回程內插路徑。
#         if not self._z_returning_home:
#             if (now - self._z_return_home_start_time) < self._z_return_home_delay_s:
#                 return

#             return_start_pose = self._target_pose.copy()
#             return_start_pose[6] = self._gripper_open_pos

#             return_mid_pose = self._z_mid_pose.copy()
#             return_mid_pose[6] = self._gripper_open_pos

#             return_home_pose = self._home_target_pose.copy()
#             return_home_pose[6] = self._gripper_open_pos

#             self._z_waypoints = []

#             # 回程不要產生太多細內插點：
#             # 放置點 -> 中間點：2 個 waypoint
#             # 中間點 -> HOME：2 個 waypoint
#             # 總共 8 個 waypoint，且夾爪維持開爪。
#             self._z_waypoints.extend(
#                 self._make_fixed_linear_waypoints(return_start_pose, return_mid_pose, 4)
#             )
#             self._z_waypoints.extend(
#                 self._make_fixed_linear_waypoints(return_mid_pose, return_home_pose, 4)
#             )

#             self._z_waypoint_index = 0
#             self._z_last_waypoint_time = now - self._z_interp_dt_s
#             self._z_returning_home = True

#             print("[KeyboardXYZTeleop] Z FLOW RETURN VIA MIDPOINT, 8 WAYPOINTS")
#             print(f"  return_mid={return_mid_pose.tolist()}")
#             print(f"  home={return_home_pose.tolist()}")
#             print(f"  return_waypoints={len(self._z_waypoints)}, dt={self._z_interp_dt_s}s")
#             return

#     def send_feedback(self, feedback):
#         self._feedback = feedback if feedback is not None else {}
#         return

#     def _make_action_dict(self):
#         return {
#             "action": {
#                 "x": float(self._target_pose[0]),
#                 "y": float(self._target_pose[1]),
#                 "z": float(self._target_pose[2]),
#                 "rx": float(self._target_pose[3]),
#                 "ry": float(self._target_pose[4]),
#                 "rz": float(self._target_pose[5]),
#                 "gripper": float(self._target_pose[6]),
#             }
#         }

#     def get_action(self):
#         now = time.perf_counter()

#         # 即使沒有新按鍵，也讓自動流程持續更新。
#         self._auto_gripper_update(now)
#         self._z_auto_flow_update(now)

#         if (now - self._last_action_time) < self._min_action_interval:
#             return self._make_action_dict()

#         key = self._read_key_nonblocking()
#         changed = False

#         if key == "w":
#             self._target_pose[0] += self.pos_step
#             self._auto_closing = False
#             self._z_flow_active = False
#             self._z_returning_home = False
#             changed = True

#         elif key == "s":
#             self._target_pose[0] -= self.pos_step
#             self._auto_closing = False
#             self._z_flow_active = False
#             self._z_returning_home = False
#             changed = True

#         elif key == "a":
#             self._target_pose[1] += self.pos_step
#             self._auto_closing = False
#             self._z_flow_active = False
#             self._z_returning_home = False
#             changed = True

#         elif key == "d":
#             self._target_pose[1] -= self.pos_step
#             self._auto_closing = False
#             self._z_flow_active = False
#             self._z_returning_home = False
#             changed = True

#         elif key == "r":
#             self._target_pose[2] += self.pos_step
#             self._auto_closing = False
#             self._z_flow_active = False
#             self._z_returning_home = False
#             changed = True

#         elif key == "f":
#             self._target_pose[2] -= self.pos_step
#             self._auto_closing = False
#             self._z_flow_active = False
#             self._z_returning_home = False
#             changed = True

#         elif key == "i":
#             self._target_pose[3] += self.rot_step
#             self._auto_closing = False
#             self._z_flow_active = False
#             self._z_returning_home = False
#             changed = True

#         elif key == "k":
#             self._target_pose[3] -= self.rot_step
#             self._auto_closing = False
#             self._z_flow_active = False
#             self._z_returning_home = False
#             changed = True

#         elif key == "o":
#             self._target_pose[4] += self.rot_step
#             self._auto_closing = False
#             self._z_flow_active = False
#             self._z_returning_home = False
#             changed = True

#         elif key == "l":
#             self._target_pose[4] -= self.rot_step
#             self._auto_closing = False
#             self._z_flow_active = False
#             self._z_returning_home = False
#             changed = True

#         elif key == "p":
#             self._target_pose[5] += self.rot_step
#             self._auto_closing = False
#             self._z_flow_active = False
#             self._z_returning_home = False
#             changed = True

#         elif key == ";":
#             self._target_pose[5] -= self.rot_step
#             self._auto_closing = False
#             self._z_flow_active = False
#             self._z_returning_home = False
#             changed = True

#         elif key == "]":
#             self._target_pose[6] = min(
#                 self._gripper_close_pos_max,
#                 self._target_pose[6] + 5.0,
#             )
#             self._auto_closing = False
#             self._z_flow_active = False
#             self._z_returning_home = False
#             changed = True

#         elif key == "[":
#             self._target_pose[6] = max(
#                 self._gripper_open_pos,
#                 self._target_pose[6] - 5.0,
#             )
#             self._auto_closing = False
#             self._z_flow_active = False
#             self._z_returning_home = False
#             changed = True

#         elif key == " ":
#             self._start_space_auto_close()
#             changed = True

#         elif key == "z":
#             self._start_z_auto_flow(now)
#             changed = True

#         elif key == "q":
#             raise KeyboardInterrupt("User pressed q")

#         # 當輪也立即更新一次。
#         self._auto_gripper_update(now)
#         self._z_auto_flow_update(now)

#         self._target_pose[6] = float(
#             np.clip(
#                 self._target_pose[6],
#                 self._gripper_open_pos,
#                 self._gripper_close_pos_max,
#             )
#         )

#         if changed or self._auto_closing or self._z_flow_active:
#             self._last_action_time = now

#         return self._make_action_dict()










import sys
import select
import termios
import tty
import time
import numpy as np

from lerobot.teleoperators.teleoperator import Teleoperator
from .configuration_keyboard_xyz import KeyboardXYZTeleopConfig


# 一般鍵盤手動控制仍是 TCP endpoint pose + gripper。
# z 自動流程會改送 joint angle + gripper，robot 端會用 JPP 執行。
STATE_NAMES = ["x", "y", "z", "rx", "ry", "rz", "gripper"]
JOINT_ACTION_NAMES = ["j1", "j2", "j3", "j4", "j5", "j6", "gripper"]

HOME_JOINT_POSE7 = np.array(
    [-103.82, 2.66, 100.21, -13.13, 89.7, -14.02, 150.0],
    dtype=np.float32,
)
Z_MID_JOINT_POSE7 = np.array(
    [-79.47, 13.81, 86.90, -10.90, 89.72, 10.34, 255.0],
    dtype=np.float32,
)
Z_TARGET_JOINT_POSE7 = np.array(
    [-79.47, 15.87, 92.93, -18.99, 89.74, 10.34, 255.0],
    dtype=np.float32,
)


class KeyboardXYZTeleop(Teleoperator):
    config_class = KeyboardXYZTeleopConfig
    name = "keyboard_xyz"

    def __init__(self, config: KeyboardXYZTeleopConfig):
        super().__init__(config)
        self.config = config
        self.pos_step = float(config.pos_step)
        self.rot_step = float(config.rot_step)

        self._is_connected = False
        self._is_calibrated = True
        self._old_term_settings = None

        # ===== control frequency =====
        self._min_action_interval = 0.1
        self._last_action_time = 0.0

        # ===== gripper settings =====
        self._gripper_step = 20.0
        self._gripper_cmd_interval = 0.1
        self._gripper_open_pos = 150.0
        self._gripper_close_pos_max = 255.0

        # ===== manual TCP target =====
        # 不再使用固定 _home_target_pose。
        # 新 episode 先用 HOME_JOINT_POSE7 走 JPP 到指定軸角，
        # 等收到安全的 /tool_pose TCP feedback 後，只同步一次到 _target_pose，
        # 之後 w/s/a/d 才從該 TCP 位置開始小幅加減。
        self._target_pose = np.array(
            [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, self._gripper_open_pos],
            dtype=np.float32,
        )
        self._manual_tcp_ready = False
        self._sync_target_from_feedback_once = False
        self._last_manual_wait_print_time = 0.0

        # ===== Z key auto flow target poses: joint angle mode =====
        # 一般鍵盤 w/s/a/d... 仍是 TCP CPP 控制。
        # 但 z 自動流程改成 joint angle 內插，送出 [j1~j6, gripper]，robot 端會用 JPP。
        self._z_home_joint_pose = HOME_JOINT_POSE7.copy()
        self._z_mid_pose = Z_MID_JOINT_POSE7.copy()
        self._z_target_pose = Z_TARGET_JOINT_POSE7.copy()
        self._z_joint_target_pose = self._z_home_joint_pose.copy()

        # 每 0.1 s 發送一個內插點。
        # z joint flow 的去程依照最大單軸角度差自動決定點數。
        self._z_interp_dt_s = 0.1
        self._z_interp_joint_step_deg = max(abs(float(self.rot_step)), 1.0)
        # 保留原本 TCP waypoint 函式可能用到的屬性，避免外部呼叫舊函式時出錯。
        self._z_interp_pos_step_mm = max(abs(float(self.pos_step)), 5.0)

        # 目前 action 輸出模式：
        # - "tcp"：一般鍵盤手動 TCP 控制，輸出 x/y/z/rx/ry/rz。
        # - "joint"：初始化、z 自動流程與回 home，輸出 j1~j6。
        # 新 episode 預設先送 home joint，等 TCP feedback 安全同步後才切成 tcp。
        self._action_mode = "joint"

        # ===== SPACE auto close only =====
        # SPACE 現在只做自動關爪，不再有「第二次空白鍵開爪回 HOME」機制。
        self._auto_closing = False
        self._auto_close_start_time = 0.0
        self._auto_close_timeout_s = 9.0
        self._last_gripper_auto_time = 0.0

        # ===== z key auto flow =====
        # z 流程：
        # current joint feedback -> joint 中間點 -> joint 放置點 -> 等待 1 s -> 開爪
        # -> 等待 1 s -> 8 個 joint waypoint 回中間點與 HOME
        self._z_flow_active = False
        self._z_flow_opened = False
        self._z_returning_home = False
        self._z_flow_start_time = 0.0
        self._z_open_start_time = 0.0
        self._z_return_home_start_time = 0.0
        self._z_open_delay_s = 1.0
        self._z_return_home_delay_s = 1.0

        self._z_waypoints = []
        self._z_waypoint_index = 0
        self._z_last_waypoint_time = 0.0

        # feedback 會用於 z joint flow 的起始關節角、夾爪回授，以及手動 TCP 起始同步。
        self._feedback = {}

    @property
    def action_features(self):
        return {
            "action": {
                "dtype": "float32",
                "shape": (7,),
                "names": STATE_NAMES,
            }
        }

    @property
    def feedback_features(self):
        return {}

    @property
    def is_connected(self):
        return self._is_connected

    @property
    def is_calibrated(self):
        return self._is_calibrated

    def configure(self):
        return

    def calibrate(self):
        self._is_calibrated = True

    def connect(self):
        if self._is_connected:
            return

        self._old_term_settings = termios.tcgetattr(sys.stdin)
        tty.setcbreak(sys.stdin.fileno())
        self._is_connected = True

        print("[KeyboardXYZTeleop] connected")
        print(
            "keys: w/s=x, d/a=y, r/f=z, "
            "i/k=rx, o/l=ry, p/;=rz, "
            "]/[]=manual gripper, SPACE=auto close, z=target/open/home flow, q=quit"
        )
        print("[KeyboardXYZTeleop] SPACE flow:")
        print("  SPACE: auto close only")
        print("[KeyboardXYZTeleop] z flow:")
        print("  z: joint interpolation to midpoint -> joint place -> wait 1s -> open gripper -> 8 joint waypoints back home")

    def disconnect(self):
        if self._old_term_settings is not None:
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self._old_term_settings)
            self._old_term_settings = None

        self._is_connected = False
        print("[KeyboardXYZTeleop] disconnected")

    def reset_for_new_episode(self):
        # 新 episode 一開始不送固定 TCP home。
        # 先輸出 home joint action，讓 robot 端用 PTP("JPP", ...) 回到指定軸角。
        # 等 send_feedback() 收到安全 /tool_pose 後，才把 _target_pose 同步成目前 TCP 並開放手動 TCP 控制。
        self._z_joint_target_pose = self._z_home_joint_pose.copy()
        self._z_joint_target_pose[6] = self._gripper_open_pos
        self._target_pose[:] = 0.0
        self._target_pose[6] = self._gripper_open_pos
        self._manual_tcp_ready = False
        self._sync_target_from_feedback_once = False
        self._last_manual_wait_print_time = 0.0

        self._auto_closing = False
        self._last_action_time = 0.0
        self._last_gripper_auto_time = 0.0
        self._auto_close_start_time = 0.0

        self._z_flow_active = False
        self._z_flow_opened = False
        self._z_returning_home = False
        self._z_flow_start_time = 0.0
        self._z_open_start_time = 0.0
        self._z_return_home_start_time = 0.0
        self._z_waypoints = []
        self._z_waypoint_index = 0
        self._z_last_waypoint_time = 0.0

        self._feedback = {}

        # 新 episode 一開始維持 joint mode；同步 TCP feedback 後才切成 tcp。
        self._action_mode = "joint"

        print(
            "[KeyboardXYZTeleop] reset_for_new_episode -> "
            f"home_joint={self._z_joint_target_pose.tolist()}, wait TCP feedback sync"
        )

    def set_home_target_pose(self, pose7):
        # 保留舊函式名稱相容外部呼叫，但現在 home 是 joint pose，不是 TCP pose。
        arr = np.asarray(pose7, dtype=np.float32).reshape(7)
        self._z_home_joint_pose = arr.copy()
        self._z_joint_target_pose = arr.copy()
        print(f"[KeyboardXYZTeleop] set_home_joint_pose -> {self._z_home_joint_pose.tolist()}")

    def set_z_mid_pose(self, pose7):
        # z flow 的 mid pose 現在是 joint angle pose，不是 TCP pose。
        arr = np.asarray(pose7, dtype=np.float32).reshape(7)
        self._z_mid_pose = arr.copy()
        print(f"[KeyboardXYZTeleop] set_z_mid_joint_pose -> {self._z_mid_pose.tolist()}")

    def set_z_target_pose(self, pose7):
        # z flow 的 target pose 現在是 joint angle pose，不是 TCP pose。
        arr = np.asarray(pose7, dtype=np.float32).reshape(7)
        self._z_target_pose = arr.copy()
        print(f"[KeyboardXYZTeleop] set_z_target_joint_pose -> {self._z_target_pose.tolist()}")

    def set_z_home_joint_pose(self, pose7):
        arr = np.asarray(pose7, dtype=np.float32).reshape(7)
        self._z_home_joint_pose = arr.copy()
        print(f"[KeyboardXYZTeleop] set_z_home_joint_pose -> {self._z_home_joint_pose.tolist()}")

    def _make_linear_waypoints(self, start_pose, end_pose):
        """
        產生 start_pose -> end_pose 的線性內插點。
        - 平移 xyz：依照 pos_step 自動決定點數。
        - 旋轉 rx ry rz：使用最短角度差，避免 -180 到 180 被插成 360 度大旋轉。
        - 回傳不包含 start_pose，只包含後續要送出的 waypoint。
        """
        start = np.asarray(start_pose, dtype=np.float32).reshape(7)
        end = np.asarray(end_pose, dtype=np.float32).reshape(7)

        pos_delta = end[:3] - start[:3]

        # Euler 角使用最短角度差，單位為 degree。
        rot_delta = (end[3:6] - start[3:6] + 180.0) % 360.0 - 180.0

        max_pos_delta = float(np.max(np.abs(pos_delta)))
        max_rot_delta = float(np.max(np.abs(rot_delta)))

        pos_step = max(float(self._z_interp_pos_step_mm), 1e-6)
        rot_step = max(abs(float(self.rot_step)), 1e-6)

        n_pos = int(np.ceil(max_pos_delta / pos_step))
        n_rot = int(np.ceil(max_rot_delta / rot_step))
        n_steps = max(1, n_pos, n_rot)

        waypoints = []
        for i in range(1, n_steps + 1):
            alpha = i / n_steps
            pose = start.copy()
            pose[:3] = start[:3] + alpha * pos_delta
            pose[3:6] = start[3:6] + alpha * rot_delta
            pose[6] = end[6]
            waypoints.append(pose.astype(np.float32))

        return waypoints

    def _make_fixed_linear_waypoints(self, start_pose, end_pose, n_steps: int):
        """
        產生固定數量的線性內插點。
        - 回程使用：放置點 -> 中間點 2 點，中間點 -> HOME 2 點，總共 8 點。
        - 回傳不包含 start_pose，包含 end_pose。
        """
        start = np.asarray(start_pose, dtype=np.float32).reshape(7)
        end = np.asarray(end_pose, dtype=np.float32).reshape(7)

        n_steps = max(1, int(n_steps))

        pos_delta = end[:3] - start[:3]
        rot_delta = (end[3:6] - start[3:6] + 180.0) % 360.0 - 180.0

        waypoints = []
        for i in range(1, n_steps + 1):
            alpha = i / n_steps
            pose = start.copy()
            pose[:3] = start[:3] + alpha * pos_delta
            pose[3:6] = start[3:6] + alpha * rot_delta
            pose[6] = end[6]
            waypoints.append(pose.astype(np.float32))

        return waypoints

    def _read_key_nonblocking(self):
        dr, _, _ = select.select([sys.stdin], [], [], 0.0)
        if not dr:
            return None

        chars = []
        while True:
            dr, _, _ = select.select([sys.stdin], [], [], 0.0)
            if not dr:
                break

            ch = sys.stdin.read(1)
            if not ch:
                break

            chars.append(ch)

        if not chars:
            return None

        return chars[-1]

    def _current_gripper_pos_from_feedback(self):
        if isinstance(self._feedback, dict):
            for key in ("gripper_pos", "gripper_position", "gripper", "gripper.pos"):
                if key in self._feedback:
                    try:
                        return float(self._feedback[key])
                    except Exception:
                        return None
        return None

    def _current_joint_pose_from_feedback(self):
        """
        z joint flow 的起點用 robot 回授的 joint_pose。
        若 feedback 還沒進來，就退回 home joint pose，避免拿 TCP target 當關節角。
        """
        if isinstance(self._feedback, dict):
            joint_pose = self._feedback.get("joint_pose", None)
            if joint_pose is not None:
                try:
                    arr = np.asarray(joint_pose, dtype=np.float32).reshape(-1)
                    if arr.shape[0] >= 6 and np.all(np.isfinite(arr[:6])):
                        out = self._z_home_joint_pose.copy()
                        out[:6] = arr[:6]
                        g = self._current_gripper_pos_from_feedback()
                        if g is not None:
                            out[6] = float(np.clip(g, self._gripper_open_pos, self._gripper_close_pos_max))
                        return out
                except Exception as e:
                    print(f"[KeyboardXYZTeleop] read joint feedback failed: {e}")

        return self._z_home_joint_pose.copy()

    def _make_joint_linear_waypoints(self, start_pose, end_pose):
        """
        產生 joint angle 線性內插點。
        - 前 6 維都是軸角 degree，直接線性內插，不做 TCP xyz/rpy 處理。
        - 回傳不包含 start_pose，只包含後續要送出的 waypoint。
        """
        start = np.asarray(start_pose, dtype=np.float32).reshape(7)
        end = np.asarray(end_pose, dtype=np.float32).reshape(7)

        joint_delta = end[:6] - start[:6]
        max_joint_delta = float(np.max(np.abs(joint_delta)))
        joint_step = max(float(self._z_interp_joint_step_deg), 1e-6)
        n_steps = max(1, int(np.ceil(max_joint_delta / joint_step)))

        waypoints = []
        for i in range(1, n_steps + 1):
            alpha = i / n_steps
            pose = start.copy()
            pose[:6] = start[:6] + alpha * joint_delta
            pose[6] = end[6]
            waypoints.append(pose.astype(np.float32))

        return waypoints

    def _make_fixed_joint_waypoints(self, start_pose, end_pose, n_steps: int):
        """固定數量的 joint angle 線性內插點。"""
        start = np.asarray(start_pose, dtype=np.float32).reshape(7)
        end = np.asarray(end_pose, dtype=np.float32).reshape(7)

        n_steps = max(1, int(n_steps))
        joint_delta = end[:6] - start[:6]

        waypoints = []
        for i in range(1, n_steps + 1):
            alpha = i / n_steps
            pose = start.copy()
            pose[:6] = start[:6] + alpha * joint_delta
            pose[6] = end[6]
            waypoints.append(pose.astype(np.float32))

        return waypoints

    def _start_space_auto_close(self):
        # SPACE：只做自動關爪，不再切換到開爪回 HOME。
        self._auto_closing = True
        self._z_flow_active = False
        self._z_flow_opened = False

        self._auto_close_start_time = time.perf_counter()
        self._last_gripper_auto_time = 0.0

        print("[KeyboardXYZTeleop] AUTO CLOSE START (9s chase to 255)")

    def _start_z_auto_flow(self, now: float):
        # z：改用 joint angle 內插，不使用 TCP waypoint。
        self._auto_closing = False
        self._action_mode = "joint"

        start_pose = self._current_joint_pose_from_feedback()
        start_pose[6] = self._gripper_close_pos_max

        mid_pose = self._z_mid_pose.copy()
        mid_pose[6] = self._gripper_close_pos_max

        place_pose = self._z_target_pose.copy()
        place_pose[6] = self._gripper_close_pos_max

        # joint 兩段路徑：
        # 1. current joint feedback -> joint midpoint
        # 2. joint midpoint -> joint place
        self._z_waypoints = []
        self._z_waypoints.extend(self._make_joint_linear_waypoints(start_pose, mid_pose))
        self._z_waypoints.extend(self._make_joint_linear_waypoints(mid_pose, place_pose))

        self._z_joint_target_pose = start_pose.copy()
        self._z_waypoint_index = 0
        self._z_last_waypoint_time = now - self._z_interp_dt_s  # 讓第一個點可以立即送出

        self._z_flow_active = True
        self._z_flow_opened = False
        self._z_returning_home = False
        self._z_flow_start_time = now
        self._z_open_start_time = 0.0
        self._z_return_home_start_time = 0.0

        print("[KeyboardXYZTeleop] Z JOINT FLOW START")
        print(f"  start_joint={start_pose.tolist()}")
        print(f"  mid_joint={mid_pose.tolist()}")
        print(f"  place_joint={place_pose.tolist()}")
        print(f"  waypoints={len(self._z_waypoints)}, dt={self._z_interp_dt_s}s")

    def _auto_gripper_update(self, now: float):
        if not self._auto_closing:
            return

        if (now - self._auto_close_start_time) > self._auto_close_timeout_s:
            self._auto_closing = False
            print("[KeyboardXYZTeleop] AUTO CLOSE STOP by timeout (9s)")
            return

        if (now - self._last_gripper_auto_time) < self._gripper_cmd_interval:
            return

        self._target_pose[6] = self._gripper_close_pos_max
        self._last_gripper_auto_time = now

    def _z_auto_flow_update(self, now: float):
        if not self._z_flow_active:
            return

        # 1) 每 0.1 s 送出下一個 joint waypoint。
        # 去程 gripper = 255；回程 gripper = 150。
        if self._z_waypoint_index < len(self._z_waypoints):
            if (now - self._z_last_waypoint_time) < self._z_interp_dt_s:
                return

            self._z_joint_target_pose = self._z_waypoints[self._z_waypoint_index].copy()
            self._action_mode = "joint"

            self._z_waypoint_index += 1
            self._z_last_waypoint_time = now

            if self._z_waypoint_index == len(self._z_waypoints):
                if self._z_returning_home:
                    # 回程 waypoint 全部送完，流程結束，但保持 joint hold，
                    # 避免下一個 loop 又送出舊 TCP target。
                    self._z_joint_target_pose = self._z_home_joint_pose.copy()
                    self._z_joint_target_pose[6] = self._gripper_open_pos

                    self._z_flow_active = False
                    self._z_flow_opened = False
                    self._z_returning_home = False
                    self._z_waypoints = []
                    self._z_waypoint_index = 0
                    self._action_mode = "joint"
                    # z 流程回 home 後不再重新同步 TCP。
                    # 本回合預期在穩定回 home 後直接結束，因此只保留 episode 開始時的初次同步。
                    print("[KeyboardXYZTeleop] Z JOINT FLOW RETURN HOME DONE")
                else:
                    # 放置路徑送完，開始等待開爪。
                    self._z_open_start_time = now
                    print("[KeyboardXYZTeleop] Z JOINT FLOW REACHED PLACE, wait 1s then open gripper")
            return

        # 2) 到放置點後，等待 1 s 再開爪。
        if not self._z_flow_opened:
            if self._z_open_start_time <= 0.0:
                self._z_open_start_time = now
                return

            if (now - self._z_open_start_time) < self._z_open_delay_s:
                return

            self._z_joint_target_pose[6] = self._gripper_open_pos
            self._action_mode = "joint"
            self._z_flow_opened = True
            self._z_return_home_start_time = now
            print("[KeyboardXYZTeleop] Z JOINT FLOW OPEN GRIPPER")
            return

        # 3) 開爪後等待 1 s，再產生「joint 放置點 -> joint 中間點 -> joint HOME」的回程內插路徑。
        if not self._z_returning_home:
            if (now - self._z_return_home_start_time) < self._z_return_home_delay_s:
                return

            return_start_pose = self._z_joint_target_pose.copy()
            return_start_pose[6] = self._gripper_open_pos

            return_mid_pose = self._z_mid_pose.copy()
            return_mid_pose[6] = self._gripper_open_pos

            return_home_pose = self._z_home_joint_pose.copy()
            return_home_pose[6] = self._gripper_open_pos

            self._z_waypoints = []

            # 回程使用 joint angle 固定 8 個 waypoint：
            # 放置點 -> 中間點：4 個 waypoint
            # 中間點 -> HOME：4 個 waypoint
            self._z_waypoints.extend(
                self._make_fixed_joint_waypoints(return_start_pose, return_mid_pose, 4)
            )
            self._z_waypoints.extend(
                self._make_fixed_joint_waypoints(return_mid_pose, return_home_pose, 4)
            )

            self._z_waypoint_index = 0
            self._z_last_waypoint_time = now - self._z_interp_dt_s
            self._z_returning_home = True
            self._action_mode = "joint"

            print("[KeyboardXYZTeleop] Z JOINT FLOW RETURN VIA MIDPOINT, 8 WAYPOINTS")
            print(f"  return_mid_joint={return_mid_pose.tolist()}")
            print(f"  home_joint={return_home_pose.tolist()}")
            print(f"  return_waypoints={len(self._z_waypoints)}, dt={self._z_interp_dt_s}s")
            return

    def _tcp_pose_is_safe(self, tcp_pose) -> bool:
        """
        只允許合理工作區內的 /tool_pose 被同步成鍵盤 TCP target。
        範圍可依現場工作區再調整；重點是擋掉像 z=1087 mm 這種異常值。
        """
        try:
            tcp = np.asarray(tcp_pose, dtype=np.float32).reshape(-1)
        except Exception:
            return False

        if tcp.shape[0] < 6 or not np.all(np.isfinite(tcp[:6])):
            return False

        x, y, z, rx, ry, rz = tcp[:6]
        if not (-800.0 <= float(x) <= 800.0):
            return False
        if not (-1000.0 <= float(y) <= 500.0):
            return False
        if not (50.0 <= float(z) <= 700.0):
            return False
        if np.max(np.abs([rx, ry, rz])) > 360.0:
            return False

        return True

    def _joint_feedback_near_home(self, max_error_deg: float = 15.0) -> bool:
        """確認 robot 大致已在 home 軸角附近，再允許同步 TCP。"""
        if not isinstance(self._feedback, dict):
            return False

        joint_pose = self._feedback.get("joint_pose", None)
        if joint_pose is None:
            return False

        try:
            joint = np.asarray(joint_pose, dtype=np.float32).reshape(-1)
        except Exception:
            return False

        if joint.shape[0] < 6 or not np.all(np.isfinite(joint[:6])):
            return False

        max_error = float(np.max(np.abs(joint[:6] - self._z_home_joint_pose[:6])))
        return max_error <= float(max_error_deg)

    def _print_wait_tcp_sync(self, reason: str):
        now = time.perf_counter()
        if (now - self._last_manual_wait_print_time) >= 1.0:
            print(f"[KeyboardXYZTeleop] waiting TCP sync before manual control: {reason}")
            self._last_manual_wait_print_time = now

    def send_feedback(self, feedback):
        # 保存 feedback 給 z joint flow、夾爪回授，以及新 episode 開始時的 TCP 起始同步。
        self._feedback = feedback if feedback is not None else {}

        # z flow 執行中不要同步 TCP，避免流程中途被切回 CPP。
        if self._z_flow_active:
            return

        # 已同步過就不要再每個 loop 追著 /tool_pose 改 _target_pose。
        if self._sync_target_from_feedback_once:
            return

        # 必須先確認手臂大致已到 home joint，再讀目前 tool_pose 作為手動 TCP 起點。
        if not self._joint_feedback_near_home():
            self._print_wait_tcp_sync("joint feedback not near home yet")
            return

        tcp_pose = self._feedback.get("tcp_pose", None)
        if tcp_pose is None:
            self._print_wait_tcp_sync("no tcp_pose feedback")
            return

        if not self._tcp_pose_is_safe(tcp_pose):
            try:
                bad = np.asarray(tcp_pose, dtype=np.float32).reshape(-1)[:6].tolist()
            except Exception:
                bad = tcp_pose
            self._print_wait_tcp_sync(f"unsafe tcp_pose={bad}")
            return

        tcp = np.asarray(tcp_pose, dtype=np.float32).reshape(-1)
        self._target_pose[:6] = tcp[:6]

        g = self._current_gripper_pos_from_feedback()
        if g is not None:
            self._target_pose[6] = float(np.clip(g, self._gripper_open_pos, self._gripper_close_pos_max))
        else:
            self._target_pose[6] = self._gripper_open_pos

        self._manual_tcp_ready = True
        self._sync_target_from_feedback_once = True
        self._action_mode = "tcp"
        print(f"[KeyboardXYZTeleop] synced TCP target once -> {self._target_pose.tolist()}")
        return

    def _make_action_dict(self):
        if self._action_mode == "joint":
            # z 自動流程用 joint action，robot 端會辨識 j1~j6 並使用 PTP("JPP", ...)。
            return {
                "action": {
                    "j1": float(self._z_joint_target_pose[0]),
                    "j2": float(self._z_joint_target_pose[1]),
                    "j3": float(self._z_joint_target_pose[2]),
                    "j4": float(self._z_joint_target_pose[3]),
                    "j5": float(self._z_joint_target_pose[4]),
                    "j6": float(self._z_joint_target_pose[5]),
                    "gripper": float(self._z_joint_target_pose[6]),
                }
            }

        # 一般鍵盤手動控制維持 TCP action。
        return {
            "action": {
                "x": float(self._target_pose[0]),
                "y": float(self._target_pose[1]),
                "z": float(self._target_pose[2]),
                "rx": float(self._target_pose[3]),
                "ry": float(self._target_pose[4]),
                "rz": float(self._target_pose[5]),
                "gripper": float(self._target_pose[6]),
            }
        }

    def get_action(self):
        now = time.perf_counter()

        # 即使沒有新按鍵，也讓自動流程持續更新。
        self._auto_gripper_update(now)
        self._z_auto_flow_update(now)

        if (now - self._last_action_time) < self._min_action_interval:
            return self._make_action_dict()

        key = self._read_key_nonblocking()
        changed = False

        # 手動 TCP 控制必須等到：
        # 1) 已用 JPP 回到 home joint；
        # 2) 已讀取安全 /tool_pose 並同步到 _target_pose。
        manual_tcp_keys = ("w", "s", "a", "d", "r", "f", "i", "k", "o", "l", "p", ";", "[", "]", " ")
        if key in manual_tcp_keys and not self._manual_tcp_ready:
            self._action_mode = "joint"
            self._z_joint_target_pose = self._z_home_joint_pose.copy()
            self._z_joint_target_pose[6] = self._gripper_open_pos
            self._print_wait_tcp_sync(f"key '{key}' ignored")
            self._last_action_time = now
            return self._make_action_dict()

        if key == "w":
            self._target_pose[0] += self.pos_step
            self._auto_closing = False
            self._z_flow_active = False
            self._z_returning_home = False
            self._action_mode = "tcp"
            changed = True

        elif key == "s":
            self._target_pose[0] -= self.pos_step
            self._auto_closing = False
            self._z_flow_active = False
            self._z_returning_home = False
            self._action_mode = "tcp"
            changed = True

        elif key == "a":
            self._target_pose[1] += self.pos_step
            self._auto_closing = False
            self._z_flow_active = False
            self._z_returning_home = False
            self._action_mode = "tcp"
            changed = True

        elif key == "d":
            self._target_pose[1] -= self.pos_step
            self._auto_closing = False
            self._z_flow_active = False
            self._z_returning_home = False
            self._action_mode = "tcp"
            changed = True

        elif key == "r":
            self._target_pose[2] += self.pos_step
            self._auto_closing = False
            self._z_flow_active = False
            self._z_returning_home = False
            self._action_mode = "tcp"
            changed = True

        elif key == "f":
            self._target_pose[2] -= self.pos_step
            self._auto_closing = False
            self._z_flow_active = False
            self._z_returning_home = False
            self._action_mode = "tcp"
            changed = True

        elif key == "i":
            self._target_pose[3] += self.rot_step
            self._auto_closing = False
            self._z_flow_active = False
            self._z_returning_home = False
            self._action_mode = "tcp"
            changed = True

        elif key == "k":
            self._target_pose[3] -= self.rot_step
            self._auto_closing = False
            self._z_flow_active = False
            self._z_returning_home = False
            self._action_mode = "tcp"
            changed = True

        elif key == "o":
            self._target_pose[4] += self.rot_step
            self._auto_closing = False
            self._z_flow_active = False
            self._z_returning_home = False
            self._action_mode = "tcp"
            changed = True

        elif key == "l":
            self._target_pose[4] -= self.rot_step
            self._auto_closing = False
            self._z_flow_active = False
            self._z_returning_home = False
            self._action_mode = "tcp"
            changed = True

        elif key == "p":
            self._target_pose[5] += self.rot_step
            self._auto_closing = False
            self._z_flow_active = False
            self._z_returning_home = False
            self._action_mode = "tcp"
            changed = True

        elif key == ";":
            self._target_pose[5] -= self.rot_step
            self._auto_closing = False
            self._z_flow_active = False
            self._z_returning_home = False
            self._action_mode = "tcp"
            changed = True

        elif key == "]":
            self._target_pose[6] = min(
                self._gripper_close_pos_max,
                self._target_pose[6] + 5.0,
            )
            self._auto_closing = False
            self._z_flow_active = False
            self._z_returning_home = False
            self._action_mode = "tcp"
            changed = True

        elif key == "[":
            self._target_pose[6] = max(
                self._gripper_open_pos,
                self._target_pose[6] - 5.0,
            )
            self._auto_closing = False
            self._z_flow_active = False
            self._z_returning_home = False
            self._action_mode = "tcp"
            changed = True

        elif key == " ":
            self._action_mode = "tcp"
            self._start_space_auto_close()
            changed = True

        elif key == "z":
            self._start_z_auto_flow(now)
            changed = True

        elif key == "q":
            raise KeyboardInterrupt("User pressed q")

        # 當輪也立即更新一次。
        self._auto_gripper_update(now)
        self._z_auto_flow_update(now)

        self._target_pose[6] = float(
            np.clip(
                self._target_pose[6],
                self._gripper_open_pos,
                self._gripper_close_pos_max,
            )
        )
        self._z_joint_target_pose[6] = float(
            np.clip(
                self._z_joint_target_pose[6],
                self._gripper_open_pos,
                self._gripper_close_pos_max,
            )
        )

        if changed or self._auto_closing or self._z_flow_active:
            self._last_action_time = now

        return self._make_action_dict()