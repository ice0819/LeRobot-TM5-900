
# import time
# import threading
# import numpy as np

# import rclpy
# from rclpy.node import Node
# from geometry_msgs.msg import PoseStamped

# from lerobot.cameras.utils import make_cameras_from_configs
# from lerobot.processor import RobotAction, RobotObservation
# from lerobot.robots.robot import Robot
# from .config_tm_follower import TMFollowerConfig

# try:
#     from tm_msgs.srv import SendScript
# except Exception:
#     SendScript = None

# # ===== gripper imports =====
# import serial
# from . import ROS2_gripper as rq


# STATE_NAMES = ["x", "y", "z", "rx", "ry", "rz", "gripper"]


# def quat_to_euler_xyz_deg(x, y, z, w):
#     t0 = +2.0 * (w * x + y * z)
#     t1 = +1.0 - 2.0 * (x * x + y * y)
#     roll = np.arctan2(t0, t1)

#     t2 = +2.0 * (w * y - z * x)
#     t2 = np.clip(t2, -1.0, 1.0)
#     pitch = np.arcsin(t2)

#     t3 = +2.0 * (w * z + x * y)
#     t4 = +1.0 - 2.0 * (y * y + z * z)
#     yaw = np.arctan2(t3, t4)

#     return np.degrees([roll, pitch, yaw]).astype(np.float32)


# class TMFollower(Robot):
#     config_class = TMFollowerConfig
#     name = "tm_follower"
#     robot_type = "tm_follower"

#     def __init__(self, config: TMFollowerConfig):
#         super().__init__(config)
#         self.config = config

#         self._is_connected = False
#         self._is_calibrated = True
#         self._lock = threading.Lock()

#         self.tool_pose_topic = config.tool_pose_topic
#         self.send_script_service = config.send_script_service

#         # [x, y, z, rx, ry, rz, gripper]
#         # xyz: mm, rpy: deg, gripper: 0~255
#         self._tcp_pose = np.array([-250.0, -500.0, 150.0, -180.0, 0.0, 0.0, 150.0], dtype=np.float32)
#         self._home_pose = np.array([-250.0, -500.0, 150.0, -180.0, 0.0, 0.0, 150.0], dtype=np.float32)

#         self.cameras = make_cameras_from_configs(config.cameras)

#         self._node = None
#         self._ros_thread = None
#         self._stop_ros = False
#         self._send_script_client = None

#         self._send_epsilon = 1e-6
#         self._min_send_interval = 0.1
#         self._last_send_time = 0.0
#         self._min_gripper_send_interval = 0.1
#         self._last_gripper_send_time = 0.0
#         # ===== gripper =====
#         self._gripper = None
#         self._gripper_port = "/dev/ttyUSB0"
#         self._gripper_slave_id = 9
#         self._gripper_speed = 128
#         self._gripper_force = 256

#         # 夾爪真實位置輪詢不要太頻繁
#         self._last_gripper_poll_time = 0.0
#         self._gripper_poll_interval = 0.5  # sec

#     @property
#     def _state_spec(self) -> dict:
#         return {
#             "dtype": "float32",
#             "shape": (7,),
#             "names": STATE_NAMES,
#         }

#     @property
#     def _cameras_ft(self) -> dict[str, tuple]:
#         return {
#             cam: (self.config.cameras[cam].height, self.config.cameras[cam].width, 3)
#             for cam in self.cameras
#         }

#     @property
#     def observation_features(self) -> dict[str, dict | tuple]:
#         return {
#             "state": self._state_spec,
#             **self._cameras_ft,
#         }

#     @property
#     def action_features(self) -> dict[str, dict]:
#         return {
#             "action": self._state_spec,
#         }

#     @property
#     def is_connected(self):
#         return self._is_connected and all(cam.is_connected for cam in self.cameras.values())

#     @property
#     def is_calibrated(self):
#         return self._is_calibrated

#     def configure(self):
#         return

#     def calibrate(self):
#         self._is_calibrated = True

#     def _tool_pose_cb(self, msg: PoseStamped):
#         p = msg.pose.position
#         q = msg.pose.orientation

#         xyz_mm = np.array([p.x, p.y, p.z], dtype=np.float32) * 1000.0
#         rpy_deg = quat_to_euler_xyz_deg(q.x, q.y, q.z, q.w)

#         with self._lock:
#             self._tcp_pose[:3] = xyz_mm
#             self._tcp_pose[3:6] = rpy_deg

#     def _ros_spin_worker(self):
#         while not self._stop_ros and rclpy.ok():
#             rclpy.spin_once(self._node, timeout_sec=0.05)

#     def _debug_gripper_status(self, tag=""):
#         if self._gripper is None:
#             # print(f"[TMFollower] {tag} gripper not initialized")
#             return

#         try:
#             self._gripper.readAll()
#             pd = self._gripper.paramDic
#             # print(
#             #     f"[TMFollower] {tag} "
#             #     f"gACT={pd.get('gACT')} "
#             #     f"gGTO={pd.get('gGTO')} "
#             #     f"gSTA={pd.get('gSTA')} "
#             #     f"gOBJ={pd.get('gOBJ')} "
#             #     f"gFLT={pd.get('gFLT')} "
#             #     f"gPR={pd.get('gPR')} "
#             #     f"gPO={pd.get('gPO')} "
#             #     f"gCU={pd.get('gCU')}"
#             # )
#         except Exception as e:
#             print(f"[TMFollower] {tag} readAll failed: {e}")

#     def _get_gripper_position_safe(self, force: bool = False) -> float:
#         if self._gripper is None:
#             with self._lock:
#                 return float(self._tcp_pose[6])

#         now = time.perf_counter()

#         # 非強制模式下，限制輪詢頻率，避免狂刷 readAll/getPosition
#         if (not force) and ((now - self._last_gripper_poll_time) < self._gripper_poll_interval):
#             with self._lock:
#                 return float(self._tcp_pose[6])

#         try:
#             pos = float(self._gripper.getPosition())
#             self._last_gripper_poll_time = now
#             with self._lock:
#                 self._tcp_pose[6] = pos
#             return pos
#         except Exception as e:
#             print(f"[TMFollower] get gripper position failed: {e}")
#             with self._lock:
#                 return float(self._tcp_pose[6])

#     def _init_gripper(self):
#         serial.Serial(self._gripper_port, 115200, timeout=1).close()

#         self._gripper = rq.RobotiqGripper(
#             portname=self._gripper_port,
#             slaveaddress=self._gripper_slave_id,
#         )

#         print("[TMFollower] Initializing gripper...")
#         self._gripper.resetActivate()
#         time.sleep(0.3)

#         self._move_gripper_absolute(0)
#         time.sleep(0.05)

#         # 同步一次真實位置
#         self._get_gripper_position_safe(force=True)
#         self._debug_gripper_status("after init")
# #####
#     def _get_gripper_current_raw_safe(self) -> float | None:
#         if self._gripper is None:
#             return None

#         try:
#             self._gripper.readAll()
#             pd = self._gripper.paramDic
#             gcu = pd.get("gCU", None)
#             if gcu is None:
#                 return None
#             return float(gcu)
#         except Exception as e:
#             print(f"[TMFollower] get gripper current raw failed: {e}")
#             return None


#     def get_teleop_feedback(self) -> dict:
#         gripper_pos = self._get_gripper_position_safe(force=False)
#         gripper_current_raw = self._get_gripper_current_raw_safe()

#         # print(f"[TMFollower] teleop_feedback pos={gripper_pos}, current_raw={gripper_current_raw}")

#         return {
#             "gripper": float(gripper_pos),
#             "gripper_pos": float(gripper_pos),
#             "gripper_position": float(gripper_pos),
#             "gripper_current_raw": gripper_current_raw,
#         }
# ####
#     def _move_gripper_absolute(self, pos_0_255: float):
#         if self._gripper is None:
#             return

#         pos = int(np.clip(round(float(pos_0_255)), 0, 255))

#         # gripper 最小發送間隔 0.1 秒
#         now = time.perf_counter()
#         elapsed = now - self._last_gripper_send_time
#         if elapsed < self._min_gripper_send_interval:
#             time.sleep(self._min_gripper_send_interval - elapsed)

#         # print(f"[TMFollower] _move_gripper_absolute -> {pos}")

#         if hasattr(self._gripper, "goto"):
#             self._gripper.goto(pos, self._gripper_speed, self._gripper_force)
#         elif hasattr(self._gripper, "goTo"):
#             self._gripper.goTo(pos, self._gripper_speed, self._gripper_force)
#         elif hasattr(self._gripper, "goTomm"):
#             self._gripper.goTomm(pos, self._gripper_speed, self._gripper_force)
#         else:
#             raise RuntimeError("Gripper object has no goto/goTo/goTomm method.")

#         self._last_gripper_send_time = time.perf_counter()

#         with self._lock:
#             self._tcp_pose[6] = float(pos)

#     def connect(self):
#         if self._is_connected:
#             return

#         if not rclpy.ok():
#             rclpy.init(args=None)

#         self._node = Node("tm_follower_robot_node")
#         self._node.create_subscription(PoseStamped, self.tool_pose_topic, self._tool_pose_cb, 10)

#         if SendScript is None:
#             raise RuntimeError("Cannot import tm_msgs.srv.SendScript. Check tm_msgs installation.")

#         self._send_script_client = self._node.create_client(SendScript, self.send_script_service)

#         print(f"[TMFollower] waiting for service: {self.send_script_service}")
#         max_wait_s = 10.0
#         t0 = time.time()
#         while not self._send_script_client.wait_for_service(timeout_sec=1.0):
#             print(f"[TMFollower] still waiting for {self.send_script_service} ...")
#             if time.time() - t0 > max_wait_s:
#                 raise RuntimeError(
#                     f"Service not found: {self.send_script_service}. Please check 'ros2 service list'."
#                 )

#         self._stop_ros = False
#         self._ros_thread = threading.Thread(target=self._ros_spin_worker, daemon=True)
#         self._ros_thread.start()

#         for cam_key, cam in self.cameras.items():
#             cam.connect()
#             print(f"[TMFollower] connected camera: {cam_key}")

#         self._init_gripper()

#         self._is_connected = True
#         print("[TMFollower] connected")
#         print(f"[TMFollower] subscribed to {self.tool_pose_topic}")

#     def disconnect(self):
#         self._is_connected = False

#         for cam_key, cam in self.cameras.items():
#             try:
#                 cam.disconnect()
#                 print(f"[TMFollower] disconnected camera: {cam_key}")
#             except Exception as e:
#                 print(f"[TMFollower] camera disconnect warning for {cam_key}: {e}")

#         self._stop_ros = True
#         if self._ros_thread is not None:
#             self._ros_thread.join(timeout=1.0)
#             self._ros_thread = None

#         if self._node is not None:
#             self._node.destroy_node()
#             self._node = None

#         if rclpy.ok():
#             rclpy.shutdown()

#         print("[TMFollower] disconnected")

#     def get_observation(self) -> RobotObservation:
#         with self._lock:
#             pose = self._tcp_pose.copy().astype(np.float32)

#         # 低頻同步真實夾爪位置，不要每個 loop 都狂讀
#         pose[6] = self._get_gripper_position_safe(force=False)

#         obs_dict = {
#             "state": pose,
#         }

#         images = {}
#         for cam_key, cam in self.cameras.items():
#             frame = cam.read_latest()
#             obs_dict[cam_key] = frame
#             if frame is not None:
#                 images[cam_key] = frame

#         if images:
#             obs_dict["obs.images"] = images
#             obs_dict["observation.images"] = images

#         return obs_dict

#     def _extract_action_array(self, action: RobotAction) -> np.ndarray:
#         if isinstance(action, dict):
#             if "action" in action:
#                 a = action["action"]
#                 if isinstance(a, dict):
#                     if not all(k in a for k in STATE_NAMES):
#                         raise KeyError(f"Action dict missing keys. Got: {list(a.keys())}")
#                     arr = np.array([float(a[k]) for k in STATE_NAMES], dtype=np.float32)
#                 else:
#                     arr = np.asarray(a, dtype=np.float32)

#             elif all(k in action for k in STATE_NAMES):
#                 arr = np.array([float(action[k]) for k in STATE_NAMES], dtype=np.float32)

#             elif all(f"action.{k}" in action for k in STATE_NAMES):
#                 arr = np.array([float(action[f'action.{k}']) for k in STATE_NAMES], dtype=np.float32)

#             else:
#                 raise KeyError(f"Unsupported action dict keys: {list(action.keys())}")
#         else:
#             arr = np.asarray(action, dtype=np.float32)

#         if arr.shape != (7,):
#             raise ValueError(f"Expected action shape (7,), got {arr.shape}")

#         return arr.astype(np.float32)

#     def _send_pose_script(self, target_pose7: np.ndarray):
#         if SendScript is None:
#             raise RuntimeError("Cannot import tm_msgs.srv.SendScript. Check tm_msgs installation.")

#         x, y, z, rx, ry, rz = target_pose7[:6].tolist()
#         script = f'PTP("CPP",{x:.3f},{y:.3f},{z:.3f},{rx:.3f},{ry:.3f},{rz:.3f},100,100,100,false)'

#         req = SendScript.Request()
#         if hasattr(req, "script"):
#             req.script = script
#         else:
#             raise RuntimeError("SendScript.Request() has no 'script' field.")

#         now = time.perf_counter()
#         elapsed = now - self._last_send_time
#         if elapsed < self._min_send_interval:
#             time.sleep(self._min_send_interval - elapsed)

#         future = self._send_script_client.call_async(req)
#         self._last_send_time = time.perf_counter()

#         start = time.time()
#         while not future.done() and (time.time() - start) < 1.0:
#             rclpy.spin_once(self._node, timeout_sec=0.01)

#         with self._lock:
#             self._tcp_pose[:6] = target_pose7[:6]

#     def reset(self):
#         if not self.is_connected:
#             raise RuntimeError("TMFollower is not connected.")

#         home_pose = self._home_pose.copy()
#         self._send_pose_script(home_pose)
#         self._move_gripper_absolute(home_pose[6])

#         time.sleep(0.3)
#         self._get_gripper_position_safe(force=True)
#         self._debug_gripper_status("after reset")
#         time.sleep(2.0)

#     def send_action(self, action: RobotAction) -> RobotAction:
#         action_arr = self._extract_action_array(action)

#         # action 改成絕對位姿:
#         # [x, y, z, rx, ry, rz, gripper]
#         target_pose = action_arr.copy().astype(np.float32)
#         target_pose[6] = np.clip(target_pose[6], 0.0, 255.0)

#         with self._lock:
#             current_pose = self._tcp_pose.copy()

#         current_gripper = self._get_gripper_position_safe(force=True)

#         tcp_changed = not np.all(np.abs(target_pose[:6] - current_pose[:6]) < self._send_epsilon)
#         now = time.perf_counter()
#         allow_resend_close = (
#             float(target_pose[6]) >= 255.0 and
#             (now - self._last_gripper_send_time) >= self._min_gripper_send_interval
#         )

#         gripper_changed = (
#             abs(float(target_pose[6]) - float(current_gripper)) >= self._send_epsilon
#             or allow_resend_close
#         )

#         if not tcp_changed and not gripper_changed:
#             return {"action": action_arr.copy()}

#         if tcp_changed:
#             self._send_pose_script(target_pose)

#         if gripper_changed:
#             self._debug_gripper_status("before")
#             self._move_gripper_absolute(target_pose[6])
#             time.sleep(0.01)
#             self._get_gripper_position_safe(force=True)
#             self._debug_gripper_status("after")

#         with self._lock:
#             self._tcp_pose[:6] = target_pose[:6]
#             self._tcp_pose[6] = float(target_pose[6])

#         return {"action": action_arr.copy()}
import time
import threading
import numpy as np

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import PoseStamped
from sensor_msgs.msg import JointState

from lerobot.cameras.utils import make_cameras_from_configs
from lerobot.processor import RobotAction, RobotObservation
from lerobot.robots.robot import Robot
from .config_tm_follower import TMFollowerConfig

try:
    from tm_msgs.srv import SendScript
except Exception:
    SendScript = None

# ===== gripper imports =====
import serial
from . import ROS2_gripper as rq


# Dataset / policy semantics: 6 軸角 + 夾爪
JOINT_STATE_NAMES = ["j1", "j2", "j3", "j4", "j5", "j6", "gripper"]
STATE_NAMES = JOINT_STATE_NAMES

# Keyboard teleop semantics: 末端 TCP 位姿 + 夾爪
TCP_ACTION_NAMES = ["x", "y", "z", "rx", "ry", "rz", "gripper"]


HOME_JOINT_POSE7 = np.array(
    [-103.82, 2.66, 100.21, -13.13, 89.7, -14.02, 150.0],
    dtype=np.float32,
)

# 這裡只作為 TCP feedback 尚未進來前的 fallback。
# 鍵盤教導仍然是 TCP 控制，所以不要把這裡改成 j1~j6 後再用 CPP 發送。
DEFAULT_TCP_HOME_POSE7 = np.array(
    [-250.0, -480.0, 370.0, -180.0, 0.0, 0.0, 150.0],
    dtype=np.float32,
)


def quat_to_euler_xyz_deg(x, y, z, w):
    t0 = +2.0 * (w * x + y * z)
    t1 = +1.0 - 2.0 * (x * x + y * y)
    roll = np.arctan2(t0, t1)

    t2 = +2.0 * (w * y - z * x)
    t2 = np.clip(t2, -1.0, 1.0)
    pitch = np.arcsin(t2)

    t3 = +2.0 * (w * z + x * y)
    t4 = +1.0 - 2.0 * (y * y + z * z)
    yaw = np.arctan2(t3, t4)

    return np.degrees([roll, pitch, yaw]).astype(np.float32)


class TMFollower(Robot):
    config_class = TMFollowerConfig
    name = "tm_follower"
    robot_type = "tm_follower"

    def __init__(self, config: TMFollowerConfig):
        super().__init__(config)
        self.config = config

        self._is_connected = False
        self._is_calibrated = True
        self._lock = threading.Lock()

        self.tool_pose_topic = config.tool_pose_topic
        self.joint_state_topic = getattr(
            config,
            "joint_states_topic",
            getattr(config, "joint_state_topic", "/joint_states"),
        )
        self.send_script_service = config.send_script_service

        # TCP feedback / TCP keyboard command target, unit: [mm, deg, gripper]
        self._tcp_pose = DEFAULT_TCP_HOME_POSE7.copy()
        self._last_tcp_target_pose = DEFAULT_TCP_HOME_POSE7[:6].copy()

        # Joint feedback / dataset state/action, unit: [deg, gripper]
        self._joint_pose = HOME_JOINT_POSE7.copy()
        self._home_joint_pose = HOME_JOINT_POSE7.copy()
        self._home_pose = self._home_joint_pose  # compatibility: reset() 使用關節 home
        self._last_joint_target_pose = HOME_JOINT_POSE7[:6].copy()
        self._last_dataset_action = HOME_JOINT_POSE7.copy()

        self.cameras = make_cameras_from_configs(config.cameras)

        self._node = None
        self._ros_thread = None
        self._stop_ros = False
        self._send_script_client = None

        self._send_epsilon = 1e-6
        self._min_send_interval = 0.1
        self._last_send_time = 0.0
        self._min_gripper_send_interval = 0.1
        self._last_gripper_send_time = 0.0
        # ===== gripper =====
        self._gripper = None
        self._gripper_port = "/dev/ttyUSB2"
        self._gripper_slave_id = 9
        self._gripper_speed = 128
        self._gripper_force = 256

        # 夾爪真實位置輪詢不要太頻繁
        self._last_gripper_poll_time = 0.0
        self._gripper_poll_interval = 0.5  # sec

        # ===== joint state filter =====
        # /joint_states 可能同時有兩個 publisher；其中一個會送出 [45,0,0,0,0,0] 假資料。
        # 這裡只影響資料紀錄用的 joint feedback，不影響 TCP 鍵盤控制。
        self._joint_feedback_initialized = False
        self._joint_jump_limit_deg = 35.0
        self._last_joint_filter_print_time = 0.0

    @property
    def _state_spec(self) -> dict:
        return {
            "dtype": "float32",
            "shape": (7,),
            "names": STATE_NAMES,
        }

    @property
    def _cameras_ft(self) -> dict[str, tuple]:
        return {
            cam: (self.config.cameras[cam].height, self.config.cameras[cam].width, 3)
            for cam in self.cameras
        }

    @property
    def observation_features(self) -> dict[str, dict | tuple]:
        return {
            "state": self._state_spec,
            **self._cameras_ft,
        }

    @property
    def action_features(self) -> dict[str, dict]:
        # Policy / dataset action 是 j1~j6，不是 TCP。
        return {
            "action": self._state_spec,
        }

    @property
    def is_connected(self):
        return self._is_connected and all(cam.is_connected for cam in self.cameras.values())

    @property
    def is_calibrated(self):
        return self._is_calibrated

    def configure(self):
        return

    def calibrate(self):
        self._is_calibrated = True

    def _tool_pose_cb(self, msg: PoseStamped):
        """TCP feedback: 只供鍵盤 TCP 教導同步 target 使用，不寫入 dataset state。"""
        p = msg.pose.position
        q = msg.pose.orientation

        xyz_mm = np.array([p.x, p.y, p.z], dtype=np.float32) * 1000.0
        rpy_deg = quat_to_euler_xyz_deg(q.x, q.y, q.z, q.w)

        with self._lock:
            self._tcp_pose[:3] = xyz_mm
            self._tcp_pose[3:6] = rpy_deg

    def _print_joint_filter_skip(self, reason: str, joint_deg: np.ndarray):
        """避免錯誤 joint state 高頻洗版，每秒最多印一次。"""
        now = time.perf_counter()
        if (now - self._last_joint_filter_print_time) >= 1.0:
            # print(f"[TMFollower] skip joint state ({reason}): {joint_deg.tolist()}")
            self._last_joint_filter_print_time = now

    def _joint_state_cb(self, msg: JointState):
        """
        Joint feedback: dataset 的 observation.state 來源。
        ROS JointState.position 通常是 rad；若數值看起來已是 degree，則直接使用。

        重要：
        你的 /joint_states 目前有兩個 tm_driver_node publisher，其中一個會交替送出：
            [0.785398, 0, 0, 0, 0, 0] rad = [45, 0, 0, 0, 0, 0] deg
        這裡會濾掉該假資料，避免 observation.state/action 被污染。
        """
        if len(msg.position) < 6:
            return

        pos = np.asarray(msg.position, dtype=np.float32)
        joint_values = None

        if msg.name:
            lower_names = [n.lower() for n in msg.name]
            name_candidates = [
                [f"joint_{i}" for i in range(1, 7)],
                [f"joint{i}" for i in range(1, 7)],
                [f"tm_joint_{i}" for i in range(1, 7)],
            ]
            for candidates in name_candidates:
                if all(name in lower_names for name in candidates):
                    idx = [lower_names.index(name) for name in candidates]
                    joint_values = pos[idx]
                    break

        if joint_values is None:
            joint_values = pos[:6]

        if not np.all(np.isfinite(joint_values)):
            return

        # TM driver 正常 JointState.position 是 rad；若輸入已像 degree，則直接使用。
        if float(np.nanmax(np.abs(joint_values))) <= (2.0 * np.pi + 0.1):
            joint_deg = np.degrees(joint_values).astype(np.float32)
        else:
            joint_deg = joint_values.astype(np.float32)

        if not np.all(np.isfinite(joint_deg)):
            return

        # 1) 擋掉目前已確認的假 joint state：[45, 0, 0, 0, 0, 0] deg。
        known_bad = np.array([45.0, 0.0, 0.0, 0.0, 0.0, 0.0], dtype=np.float32)
        if np.allclose(joint_deg, known_bad, atol=1.0):
            self._print_joint_filter_skip("known fake [45,0,0,0,0,0]", joint_deg)
            return

        # 2) 擋掉「只有 j1 約 45 度、其他軸接近 0」且 effort 幾乎全 0 的假資料。
        if len(msg.effort) >= 6:
            effort = np.asarray(msg.effort[:6], dtype=np.float32)
            fake_like_position = (
                abs(float(joint_deg[0]) - 45.0) <= 1.0
                and np.max(np.abs(joint_deg[1:6])) <= 1.0
            )
            fake_like_effort = np.all(np.abs(effort) <= 1e-3)
            if fake_like_position and fake_like_effort:
                self._print_joint_filter_skip("zero-effort fake joint state", joint_deg)
                return

        # 3) 擋掉瞬間大跳變。真實機械手臂連續回授不應該在相鄰 callback 跳超過 35 度。
        with self._lock:
            prev_joint_deg = self._joint_pose[:6].copy()
            initialized = self._joint_feedback_initialized

        if initialized:
            max_jump = float(np.max(np.abs(joint_deg - prev_joint_deg)))
            if max_jump > self._joint_jump_limit_deg:
                self._print_joint_filter_skip(f"large jump {max_jump:.2f} deg", joint_deg)
                return

        with self._lock:
            self._joint_pose[:6] = joint_deg
            self._joint_feedback_initialized = True

    def _ros_spin_worker(self):
        while not self._stop_ros and rclpy.ok():
            rclpy.spin_once(self._node, timeout_sec=0.05)

    def _debug_gripper_status(self, tag=""):
        if self._gripper is None:
            # print(f"[TMFollower] {tag} gripper not initialized")
            return

        try:
            self._gripper.readAll()
            pd = self._gripper.paramDic
            # print(
            #     f"[TMFollower] {tag} "
            #     f"gACT={pd.get('gACT')} "
            #     f"gGTO={pd.get('gGTO')} "
            #     f"gSTA={pd.get('gSTA')} "
            #     f"gOBJ={pd.get('gOBJ')} "
            #     f"gFLT={pd.get('gFLT')} "
            #     f"gPR={pd.get('gPR')} "
            #     f"gPO={pd.get('gPO')} "
            #     f"gCU={pd.get('gCU')}"
            # )
        except Exception as e:
            print(f"[TMFollower] {tag} readAll failed: {e}")

    def _sync_gripper_cache(self, pos: float):
        with self._lock:
            self._tcp_pose[6] = float(pos)
            self._joint_pose[6] = float(pos)

    def _get_gripper_position_safe(self, force: bool = False) -> float:
        if self._gripper is None:
            with self._lock:
                return float(self._joint_pose[6])

        now = time.perf_counter()

        # 非強制模式下，限制輪詢頻率，避免狂刷 readAll/getPosition
        if (not force) and ((now - self._last_gripper_poll_time) < self._gripper_poll_interval):
            with self._lock:
                return float(self._joint_pose[6])

        try:
            pos = float(self._gripper.getPosition())
            self._last_gripper_poll_time = now
            self._sync_gripper_cache(pos)
            return pos
        except Exception as e:
            print(f"[TMFollower] get gripper position failed: {e}")
            with self._lock:
                return float(self._joint_pose[6])

    def _init_gripper(self):
        serial.Serial(self._gripper_port, 115200, timeout=1).close()

        self._gripper = rq.RobotiqGripper(
            portname=self._gripper_port,
            slaveaddress=self._gripper_slave_id,
        )

        print("[TMFollower] Initializing gripper...")
        self._gripper.resetActivate()
        time.sleep(0.3)

        self._move_gripper_absolute(0)
        time.sleep(0.05)

        # 同步一次真實位置
        self._get_gripper_position_safe(force=True)
        self._debug_gripper_status("after init")

    def _get_gripper_current_raw_safe(self) -> float | None:
        if self._gripper is None:
            return None

        try:
            self._gripper.readAll()
            pd = self._gripper.paramDic
            gcu = pd.get("gCU", None)
            if gcu is None:
                return None
            return float(gcu)
        except Exception as e:
            print(f"[TMFollower] get gripper current raw failed: {e}")
            return None

    def get_teleop_feedback(self) -> dict:
        """給 keyboard teleop 使用；TCP 控制需要知道目前末端回授。"""
        gripper_pos = self._get_gripper_position_safe(force=False)
        gripper_current_raw = self._get_gripper_current_raw_safe()

        with self._lock:
            tcp_pose = self._tcp_pose.copy().astype(np.float32)
            joint_pose = self._joint_pose.copy().astype(np.float32)

        return {
            "gripper": float(gripper_pos),
            "gripper_pos": float(gripper_pos),
            "gripper_position": float(gripper_pos),
            "gripper_current_raw": gripper_current_raw,
            "tcp_pose": tcp_pose,
            "joint_pose": joint_pose,
        }

    def _move_gripper_absolute(self, pos_0_255: float):
        if self._gripper is None:
            return

        pos = int(np.clip(round(float(pos_0_255)), 0, 255))

        # gripper 最小發送間隔 0.1 秒
        now = time.perf_counter()
        elapsed = now - self._last_gripper_send_time
        if elapsed < self._min_gripper_send_interval:
            time.sleep(self._min_gripper_send_interval - elapsed)

        # print(f"[TMFollower] _move_gripper_absolute -> {pos}")

        if hasattr(self._gripper, "goto"):
            self._gripper.goto(pos, self._gripper_speed, self._gripper_force)
        elif hasattr(self._gripper, "goTo"):
            self._gripper.goTo(pos, self._gripper_speed, self._gripper_force)
        elif hasattr(self._gripper, "goTomm"):
            self._gripper.goTomm(pos, self._gripper_speed, self._gripper_force)
        else:
            raise RuntimeError("Gripper object has no goto/goTo/goTomm method.")

        self._last_gripper_send_time = time.perf_counter()
        self._sync_gripper_cache(float(pos))

    def connect(self):
        if self._is_connected:
            return

        if not rclpy.ok():
            rclpy.init(args=None)

        self._node = Node("tm_follower_robot_node")
        self._node.create_subscription(PoseStamped, self.tool_pose_topic, self._tool_pose_cb, 10)
        self._node.create_subscription(JointState, self.joint_state_topic, self._joint_state_cb, 10)

        if SendScript is None:
            raise RuntimeError("Cannot import tm_msgs.srv.SendScript. Check tm_msgs installation.")

        self._send_script_client = self._node.create_client(SendScript, self.send_script_service)

        print(f"[TMFollower] waiting for service: {self.send_script_service}")
        max_wait_s = 10.0
        t0 = time.time()
        while not self._send_script_client.wait_for_service(timeout_sec=1.0):
            print(f"[TMFollower] still waiting for {self.send_script_service} ...")
            if time.time() - t0 > max_wait_s:
                raise RuntimeError(
                    f"Service not found: {self.send_script_service}. Please check 'ros2 service list'."
                )

        self._stop_ros = False
        self._ros_thread = threading.Thread(target=self._ros_spin_worker, daemon=True)
        self._ros_thread.start()

        for cam_key, cam in self.cameras.items():
            cam.connect()
            print(f"[TMFollower] connected camera: {cam_key}")

        self._init_gripper()

        self._is_connected = True
        print("[TMFollower] connected")
        print(f"[TMFollower] subscribed to TCP feedback: {self.tool_pose_topic}")
        print(f"[TMFollower] subscribed to joint feedback: {self.joint_state_topic}")

    def disconnect(self):
        self._is_connected = False

        for cam_key, cam in self.cameras.items():
            try:
                cam.disconnect()
                print(f"[TMFollower] disconnected camera: {cam_key}")
            except Exception as e:
                print(f"[TMFollower] camera disconnect warning for {cam_key}: {e}")

        self._stop_ros = True
        if self._ros_thread is not None:
            self._ros_thread.join(timeout=1.0)
            self._ros_thread = None

        if self._node is not None:
            self._node.destroy_node()
            self._node = None

        if rclpy.ok():
            rclpy.shutdown()

        print("[TMFollower] disconnected")

    def get_observation(self) -> RobotObservation:
        with self._lock:
            pose = self._joint_pose.copy().astype(np.float32)

        # observation.state = [j1, j2, j3, j4, j5, j6, gripper]
        pose[6] = self._get_gripper_position_safe(force=False)

        obs_dict = {
            "state": pose,
        }

        images = {}
        for cam_key, cam in self.cameras.items():
            frame = cam.read_latest()
            obs_dict[cam_key] = frame
            if frame is not None:
                images[cam_key] = frame

        if images:
            obs_dict["obs.images"] = images
            obs_dict["observation.images"] = images

        return obs_dict

    def get_dataset_action(self) -> np.ndarray:
        """
        record.py 會呼叫這個函式，把 action 欄位寫成 j1~j6。
        - keyboard teleop 時：send_action(TCP) 後，這裡回傳最近 joint feedback。
        - policy inference 時：send_action(JPP) 後，這裡回傳最近 joint command。
        """
        with self._lock:
            return self._last_dataset_action.copy().astype(np.float32)

    def _extract_action_array_and_mode(self, action: RobotAction) -> tuple[np.ndarray, str]:
        """
        回傳 (arr, mode)。
        mode='tcp'：鍵盤教導，arr=[x,y,z,rx,ry,rz,gripper]，用 CPP 發送。
        mode='joint'：ACT policy，arr=[j1,j2,j3,j4,j5,j6,gripper]，用 JPP 發送。
        """
        def from_mapping(mapping):
            if all(k in mapping for k in TCP_ACTION_NAMES):
                return np.array([float(mapping[k]) for k in TCP_ACTION_NAMES], dtype=np.float32), "tcp"
            if all(k in mapping for k in JOINT_STATE_NAMES):
                return np.array([float(mapping[k]) for k in JOINT_STATE_NAMES], dtype=np.float32), "joint"
            if all(f"action.{k}" in mapping for k in TCP_ACTION_NAMES):
                return np.array([float(mapping[f"action.{k}"]) for k in TCP_ACTION_NAMES], dtype=np.float32), "tcp"
            if all(f"action.{k}" in mapping for k in JOINT_STATE_NAMES):
                return np.array([float(mapping[f"action.{k}"]) for k in JOINT_STATE_NAMES], dtype=np.float32), "joint"
            raise KeyError(f"Unsupported action dict keys: {list(mapping.keys())}")

        if isinstance(action, dict):
            if "action" in action:
                a = action["action"]
                if isinstance(a, dict):
                    arr, mode = from_mapping(a)
                else:
                    arr = np.asarray(a, dtype=np.float32)
                    # ndarray 沒有名稱時無法百分百判斷；policy/dataset 預設視為 joint。
                    # 若 teleop 被 processor 轉成 ndarray，且 TCP 的 y/z 超過 360，才自動視為 TCP。
                    mode = "tcp" if float(np.nanmax(np.abs(arr[:6]))) > 360.0 else "joint"
            else:
                arr, mode = from_mapping(action)
        else:
            arr = np.asarray(action, dtype=np.float32)
            mode = "tcp" if float(np.nanmax(np.abs(arr[:6]))) > 360.0 else "joint"

        if arr.shape != (7,):
            raise ValueError(f"Expected action shape (7,), got {arr.shape}")

        return arr.astype(np.float32), mode

    def _call_send_script(self, script: str):
        if SendScript is None:
            raise RuntimeError("Cannot import tm_msgs.srv.SendScript. Check tm_msgs installation.")

        req = SendScript.Request()
        if hasattr(req, "script"):
            req.script = script
        else:
            raise RuntimeError("SendScript.Request() has no 'script' field.")

        now = time.perf_counter()
        elapsed = now - self._last_send_time
        if elapsed < self._min_send_interval:
            time.sleep(self._min_send_interval - elapsed)

        future = self._send_script_client.call_async(req)
        self._last_send_time = time.perf_counter()

        start = time.time()
        while not future.done() and (time.time() - start) < 1.0:
            rclpy.spin_once(self._node, timeout_sec=0.01)

    def _send_tcp_pose_script(self, target_pose7: np.ndarray):
        x, y, z, rx, ry, rz = target_pose7[:6].tolist()
        script = f'PTP("CPP",{x:.3f},{y:.3f},{z:.3f},{rx:.3f},{ry:.3f},{rz:.3f},100,100,100,false)'
        self._call_send_script(script)
        with self._lock:
            self._last_tcp_target_pose = target_pose7[:6].copy()
            # 這只是 target cache；真實 TCP 仍以 /tool_pose 更新為準。
            self._tcp_pose[:6] = target_pose7[:6]

    def _send_joint_pose_script(self, target_pose7: np.ndarray):
        j1, j2, j3, j4, j5, j6 = target_pose7[:6].tolist()
        script = f'PTP("JPP",{j1:.3f},{j2:.3f},{j3:.3f},{j4:.3f},{j5:.3f},{j6:.3f},100,100,100,false)'
        self._call_send_script(script)
        with self._lock:
            self._last_joint_target_pose = target_pose7[:6].copy()

    def reset(self):
        if not self.is_connected:
            raise RuntimeError("TMFollower is not connected.")

        # reset 用關節角 home，避免 TCP IK 造成不同解。
        home_pose = self._home_joint_pose.copy()
        self._send_joint_pose_script(home_pose)
        self._move_gripper_absolute(home_pose[6])

        with self._lock:
            self._last_dataset_action = home_pose.copy()

        time.sleep(0.3)
        self._get_gripper_position_safe(force=True)
        self._debug_gripper_status("after reset")
        time.sleep(2.0)

    def send_action(self, action: RobotAction) -> RobotAction:
        action_arr, mode = self._extract_action_array_and_mode(action)

        target_pose = action_arr.copy().astype(np.float32)
        target_pose[6] = np.clip(target_pose[6], 0.0, 255.0)

        current_gripper = self._get_gripper_position_safe(force=True)
        now = time.perf_counter()
        allow_resend_close = (
            float(target_pose[6]) >= 255.0 and
            (now - self._last_gripper_send_time) >= self._min_gripper_send_interval
        )
        gripper_changed = (
            abs(float(target_pose[6]) - float(current_gripper)) >= self._send_epsilon
            or allow_resend_close
        )

        if mode == "tcp":
            with self._lock:
                last_arm_target = self._last_tcp_target_pose.copy()
            arm_changed = not np.all(np.abs(target_pose[:6] - last_arm_target) < self._send_epsilon)
            if arm_changed:
                self._send_tcp_pose_script(target_pose)
        else:
            with self._lock:
                last_arm_target = self._last_joint_target_pose.copy()
            arm_changed = not np.all(np.abs(target_pose[:6] - last_arm_target) < self._send_epsilon)
            if arm_changed:
                self._send_joint_pose_script(target_pose)

        if gripper_changed:
            self._debug_gripper_status("before")
            self._move_gripper_absolute(target_pose[6])
            time.sleep(0.01)
            self._get_gripper_position_safe(force=True)
            self._debug_gripper_status("after")

        # dataset action 統一存成 joint angle + gripper。
        with self._lock:
            if mode == "joint":
                dataset_action = target_pose.copy()
            else:
                dataset_action = self._joint_pose.copy()
                dataset_action[6] = float(target_pose[6])

            self._joint_pose[6] = float(target_pose[6])
            self._tcp_pose[6] = float(target_pose[6])
            self._last_dataset_action = dataset_action.astype(np.float32)

        return {"action": self._last_dataset_action.copy()}