
# import logging
# import time
# from dataclasses import asdict, dataclass, field
# from pathlib import Path
# from pprint import pformat
# from typing import Any

# import numpy as np

# from lerobot.cameras import (  # noqa: F401
#     CameraConfig,  # noqa: F401
# )
# from lerobot.cameras.opencv.configuration_opencv import OpenCVCameraConfig  # noqa: F401
# from lerobot.cameras.reachy2_camera.configuration_reachy2_camera import Reachy2CameraConfig  # noqa: F401
# from lerobot.cameras.realsense.configuration_realsense import RealSenseCameraConfig  # noqa: F401
# from lerobot.cameras.zmq.configuration_zmq import ZMQCameraConfig  # noqa: F401
# from lerobot.configs import parser
# from lerobot.configs.policies import PreTrainedConfig
# from lerobot.datasets.image_writer import safe_stop_image_writer
# from lerobot.datasets.lerobot_dataset import LeRobotDataset
# from lerobot.datasets.utils import build_dataset_frame
# from lerobot.datasets.video_utils import VideoEncodingManager
# from lerobot.policies.factory import make_policy, make_pre_post_processors
# from lerobot.policies.pretrained import PreTrainedPolicy
# from lerobot.policies.utils import make_robot_action
# from lerobot.robots.tm_follower import TMFollowerConfig, TMFollower
# from lerobot.teleoperators.keyboard_xyz import KeyboardXYZTeleopConfig, KeyboardXYZTeleop
# from lerobot.teleoperators.hand_gesture_xyz import HandGestureXYZTeleopConfig, HandGestureXYZTeleop
# from lerobot.processor import (
#     PolicyAction,
#     PolicyProcessorPipeline,
#     RobotAction,
#     RobotObservation,
#     RobotProcessorPipeline,
#     make_default_processors,
# )
# from lerobot.processor.rename_processor import rename_stats
# from lerobot.robots import (  # noqa: F401
#     Robot,
#     RobotConfig,
#     bi_openarm_follower,
#     bi_so_follower,
#     earthrover_mini_plus,
#     hope_jr,
#     koch_follower,
#     make_robot_from_config,
#     omx_follower,
#     openarm_follower,
#     reachy2,
#     so_follower,
#     unitree_g1 as unitree_g1_robot,
# )
# from lerobot.teleoperators import (  # noqa: F401
#     Teleoperator,
#     TeleoperatorConfig,
#     bi_openarm_leader,
#     bi_so_leader,
#     homunculus,
#     koch_leader,
#     make_teleoperator_from_config,
#     omx_leader,
#     openarm_leader,
#     reachy2_teleoperator,
#     so_leader,
#     unitree_g1,
# )
# from lerobot.teleoperators.keyboard.teleop_keyboard import KeyboardTeleop
# from lerobot.utils.constants import ACTION, OBS_STR
# from lerobot.utils.control_utils import (
#     init_keyboard_listener,
#     is_headless,
#     predict_action,
#     sanity_check_dataset_name,
#     sanity_check_dataset_robot_compatibility,
# )
# from lerobot.utils.import_utils import register_third_party_plugins
# from lerobot.utils.robot_utils import precise_sleep
# from lerobot.utils.utils import (
#     get_safe_torch_device,
#     init_logging,
#     log_say,
# )
# from lerobot.utils.visualization_utils import init_rerun, log_rerun_data


# STATE_NAMES = ["x", "y", "z", "rx", "ry", "rz", "gripper"]


# @dataclass
# class DatasetRecordConfig:
#     repo_id: str
#     single_task: str
#     root: str | Path | None = None
#     fps: int = 10
#     episode_time_s: int | float = 25
#     reset_time_s: int | float = 1
#     num_episodes: int = 50
#     video: bool = True
#     push_to_hub: bool = False
#     private: bool = True
#     tags: list[str] | None = None
#     num_image_writer_processes: int = 8
#     num_image_writer_threads_per_camera: int = 1
#     video_encoding_batch_size: int = 1
#     vcodec: str = "h264"
#     rename_map: dict[str, str] = field(default_factory=dict)

#     def __post_init__(self):
#         if self.single_task is None:
#             raise ValueError("You need to provide a task as argument in `single_task`.")


# @dataclass
# class RecordConfig:
#     robot: RobotConfig
#     dataset: DatasetRecordConfig
#     teleop: TeleoperatorConfig | None = None
#     policy: PreTrainedConfig | None = None
#     display_data: bool = False
#     display_ip: str | None = None
#     display_port: int | None = None
#     display_compressed_images: bool = False
#     play_sounds: bool = True
#     resume: bool = False

#     def __post_init__(self):
#         policy_path = parser.get_path_arg("policy")

#         if policy_path:
#             cli_overrides = parser.get_cli_overrides("policy")
#             self.policy = PreTrainedConfig.from_pretrained(policy_path, cli_overrides=cli_overrides)
#             self.policy.pretrained_path = policy_path

#         if self.teleop is None and self.policy is None:
#             raise ValueError("Choose a policy, a teleoperator or both to control the robot")

#     @classmethod
#     def __get_path_fields__(cls) -> list[str]:
#         return ["policy"]


# def build_tm_dataset_features(robot: Robot) -> dict[str, dict[str, Any]]:
#     features: dict[str, dict[str, Any]] = {
#         "action": {
#             "dtype": "float32",
#             "shape": (7,),
#             "names": STATE_NAMES,
#         },
#         "observation.state": {
#             "dtype": "float32",
#             "shape": (7,),
#             "names": STATE_NAMES,
#         },
#     }

#     for cam_name in getattr(robot, "cameras", {}).keys():
#         spec = robot.observation_features[cam_name]
#         if not isinstance(spec, tuple) or len(spec) != 3:
#             raise TypeError(f"Camera feature for {cam_name} should be (H, W, 3), got {spec}")
#         features[f"observation.images.{cam_name}"] = {
#             "dtype": "video",
#             "shape": spec,
#             "names": ["height", "width", "channel"],
#         }

#     return features


# def vec_to_named_dict(vec: np.ndarray) -> dict[str, float]:
#     arr = np.asarray(vec, dtype=np.float32)
#     if arr.shape != (len(STATE_NAMES),):
#         raise ValueError(f"Expected shape ({len(STATE_NAMES)},), got {arr.shape}")
#     return {name: float(arr[i]) for i, name in enumerate(STATE_NAMES)}


# def _extract_tm_state(obs_like: Any) -> np.ndarray:
#     if isinstance(obs_like, dict):
#         if "state" in obs_like:
#             state_val = obs_like["state"]
#             if isinstance(state_val, dict):
#                 arr = np.asarray([state_val[k] for k in STATE_NAMES], dtype=np.float32)
#             else:
#                 arr = np.asarray(state_val, dtype=np.float32)
#         elif all(k in obs_like for k in STATE_NAMES):
#             arr = np.asarray([obs_like[k] for k in STATE_NAMES], dtype=np.float32)
#         elif all(f"observation.{k}" in obs_like for k in STATE_NAMES):
#             arr = np.asarray([obs_like[f"observation.{k}"] for k in STATE_NAMES], dtype=np.float32)
#         else:
#             raise KeyError(f"Cannot extract TM state from keys: {list(obs_like.keys())}")
#     else:
#         arr = np.asarray(obs_like, dtype=np.float32)

#     if arr.shape != (len(STATE_NAMES),):
#         raise ValueError(f"TM state must have shape ({len(STATE_NAMES)},), got {arr.shape}")
#     return arr.astype(np.float32)


# def _extract_tm_images(obs_processed: Any, obs_raw: Any, robot: Robot) -> dict[str, Any]:
#     required = list(getattr(robot, "cameras", {}).keys())
#     if not required:
#         return {}

#     candidates = []
#     if isinstance(obs_processed, dict):
#         candidates.extend([
#             obs_processed.get("observation.images", None),
#             obs_processed.get("obs.images", None),
#         ])
#     if isinstance(obs_raw, dict):
#         candidates.extend([
#             obs_raw.get("observation.images", None),
#             obs_raw.get("obs.images", None),
#         ])

#     for cand in candidates:
#         if isinstance(cand, dict) and all(k in cand and cand[k] is not None for k in required):
#             return {k: cand[k] for k in required}

#     out = {}
#     srcs = []
#     if isinstance(obs_processed, dict):
#         srcs.append(obs_processed)
#     if isinstance(obs_raw, dict):
#         srcs.append(obs_raw)

#     for k in required:
#         found = None
#         for src in srcs:
#             if k in src and src[k] is not None:
#                 found = src[k]
#                 break
#         if found is None:
#             raise ValueError(f"Missing frame for required camera '{k}'")
#         out[k] = found

#     return out


# def normalize_tm_observation_for_dataset(
#     obs_raw: RobotObservation,
#     obs_processed: RobotObservation,
#     robot: Robot,
# ) -> dict[str, Any]:
#     state_vec = _extract_tm_state(obs_processed if obs_processed is not None else obs_raw)
#     state_named = vec_to_named_dict(state_vec)
#     images = _extract_tm_images(obs_processed, obs_raw, robot)

#     out = dict(state_named)

#     if images:
#         out["observation.images"] = images
#         out["obs.images"] = images
#         for k, v in images.items():
#             out[k] = v

#     return out


# def _extract_tm_action_vector(action_like: Any) -> np.ndarray:
#     if isinstance(action_like, dict):
#         if "action" in action_like:
#             a = action_like["action"]
#             if isinstance(a, dict):
#                 if not all(k in a for k in STATE_NAMES):
#                     raise KeyError(f"Action dict missing keys. Got: {list(a.keys())}")
#                 arr = np.asarray([a[k] for k in STATE_NAMES], dtype=np.float32)
#             else:
#                 arr = np.asarray(a, dtype=np.float32)
#         elif all(k in action_like for k in STATE_NAMES):
#             arr = np.asarray([action_like[k] for k in STATE_NAMES], dtype=np.float32)
#         elif all(f"action.{k}" in action_like for k in STATE_NAMES):
#             arr = np.asarray([action_like[f"action.{k}"] for k in STATE_NAMES], dtype=np.float32)
#         else:
#             raise KeyError(f"Cannot extract TM action from keys: {list(action_like.keys())}")
#     else:
#         arr = np.asarray(action_like, dtype=np.float32)

#     if arr.shape != (len(STATE_NAMES),):
#         raise ValueError(f"TM action must have shape ({len(STATE_NAMES)},), got {arr.shape}")
#     return arr.astype(np.float32)


# @safe_stop_image_writer
# def record_loop(
#     robot: Robot,
#     events: dict,
#     fps: int,
#     teleop_action_processor: RobotProcessorPipeline[
#         tuple[RobotAction, RobotObservation], RobotAction
#     ],
#     robot_action_processor: RobotProcessorPipeline[
#         tuple[RobotAction, RobotObservation], RobotAction
#     ],
#     robot_observation_processor: RobotProcessorPipeline[
#         RobotObservation, RobotObservation
#     ],
#     dataset: LeRobotDataset | None = None,
#     teleop: Teleoperator | list[Teleoperator] | None = None,
#     policy: PreTrainedPolicy | None = None,
#     preprocessor: PolicyProcessorPipeline[dict[str, Any], dict[str, Any]] | None = None,
#     postprocessor: PolicyProcessorPipeline[PolicyAction, PolicyAction] | None = None,
#     control_time_s: int | None = None,
#     single_task: str | None = None,
#     display_data: bool = False,
#     display_compressed_images: bool = False,
# ):
#     if dataset is not None and dataset.fps != fps:
#         raise ValueError(f"The dataset fps should be equal to requested fps ({dataset.fps} != {fps}).")

#     teleop_arm = teleop_keyboard = None
#     if isinstance(teleop, list):
#         teleop_keyboard = next((t for t in teleop if isinstance(t, KeyboardTeleop)), None)
#         teleop_arm = next(
#             (
#                 t
#                 for t in teleop
#                 if isinstance(
#                     t,
#                     (
#                         so_leader.SO100Leader
#                         | so_leader.SO101Leader
#                         | koch_leader.KochLeader
#                         | omx_leader.OmxLeader
#                     ),
#                 )
#             ),
#             None,
#         )

#         if not (teleop_arm and teleop_keyboard and len(teleop) == 2 and robot.name == "lekiwi_client"):
#             raise ValueError(
#                 "For multi-teleop, the list must contain exactly one KeyboardTeleop and one arm teleoperator. Currently only supported for LeKiwi robot."
#             )

#     if policy is not None and preprocessor is not None and postprocessor is not None:
#         policy.reset()
#         preprocessor.reset()
#         postprocessor.reset()

#     timestamp = 0
#     start_episode_t = time.perf_counter()

#     while timestamp < control_time_s:
#         start_loop_t = time.perf_counter()

#         if events["exit_early"]:
#             events["exit_early"] = False
#             break

#         obs = robot.get_observation()
#         obs_processed = robot_observation_processor(obs)

#         tm_obs_for_dataset = normalize_tm_observation_for_dataset(obs, obs_processed, robot)
#         if not hasattr(record_loop, "_dbg_obs_once"):
#             record_loop._dbg_obs_once = True
#             # logging.info(f"[tm debug] tm_obs_for_dataset keys = {list(tm_obs_for_dataset.keys())}")
#             # logging.info(
#             #     f"[tm debug] tm_obs_for_dataset[state] = "
#             #     f"{ {k: tm_obs_for_dataset[k] for k in STATE_NAMES if k in tm_obs_for_dataset} }"
#             # )

#         observation_frame = None

#         if policy is not None or dataset is not None:
#             observation_frame = build_dataset_frame(dataset.features, tm_obs_for_dataset, prefix=OBS_STR)

#         if policy is not None and preprocessor is not None and postprocessor is not None:
#             action_values = predict_action(
#                 observation=observation_frame,
#                 policy=policy,
#                 device=get_safe_torch_device(policy.config.device),
#                 preprocessor=preprocessor,
#                 postprocessor=postprocessor,
#                 use_amp=policy.config.use_amp,
#                 task=single_task,
#                 robot_type=robot.robot_type,
#             )
#             act_processed_policy: RobotAction = make_robot_action(action_values, dataset.features)
# #####
#         elif policy is None and isinstance(teleop, Teleoperator):
#             if hasattr(robot, "get_teleop_feedback") and hasattr(teleop, "send_feedback"):
#                 teleop.send_feedback(robot.get_teleop_feedback())

#             act = teleop.get_action()
#             act_processed_teleop = teleop_action_processor((act, obs))
# ######
#         elif policy is None and isinstance(teleop, list):
#             arm_action = teleop_arm.get_action()
#             arm_action = {f"arm_{k}": v for k, v in arm_action.items()}
#             keyboard_action = teleop_keyboard.get_action()
#             base_action = robot._from_keyboard_to_base_action(keyboard_action)
#             act = {**arm_action, **base_action} if len(base_action) > 0 else arm_action
#             act_processed_teleop = teleop_action_processor((act, obs))
#         else:
#             logging.info(
#                 "No policy or teleoperator provided, skipping action generation."
#                 "This is likely to happen when resetting the environment without a teleop device."
#                 "The robot won't be at its rest position at the start of the next episode."
#             )
#             continue

#         if policy is not None and act_processed_policy is not None:
#             action_values = act_processed_policy
#             robot_action_to_send = robot_action_processor((act_processed_policy, obs))
#         else:
#             action_values = act_processed_teleop
#             robot_action_to_send = robot_action_processor((act_processed_teleop, obs))

#         _sent_action = robot.send_action(robot_action_to_send)

#         tm_action_vec = _extract_tm_action_vector(action_values)
#         tm_action_named = vec_to_named_dict(tm_action_vec)

#         if not hasattr(record_loop, "_dbg_act_once"):
#             record_loop._dbg_act_once = True
#             # logging.info(f"[tm debug] tm_action_named = {tm_action_named}")

#         if dataset is not None:
#             action_frame = build_dataset_frame(dataset.features, tm_action_named, prefix=ACTION)
#             frame = {**observation_frame, **action_frame, "task": single_task}
#             # print(
#             #     f"action.gripper={tm_action_named['gripper']}, "
#             #     f"obs.gripper={tm_obs_for_dataset['gripper']}"
#             # )
#             dataset.add_frame(frame)

#         if display_data:
#             log_rerun_data(
#                 observation=tm_obs_for_dataset,
#                 action=tm_action_vec,
#                 compress_images=display_compressed_images,
#             )

#         dt_s = time.perf_counter() - start_loop_t
#         precise_sleep(max(1 / fps - dt_s, 0.0))
#         timestamp = time.perf_counter() - start_episode_t


# @parser.wrap()
# def record(cfg: RecordConfig) -> LeRobotDataset:
#     init_logging()
#     logging.info(pformat(asdict(cfg)))

#     if cfg.display_data:
#         init_rerun(session_name="recording", ip=cfg.display_ip, port=cfg.display_port)

#     display_compressed_images = (
#         True
#         if (cfg.display_data and cfg.display_ip is not None and cfg.display_port is not None)
#         else cfg.display_compressed_images
#     )

#     robot = make_robot_from_config(cfg.robot)
#     teleop = make_teleoperator_from_config(cfg.teleop) if cfg.teleop is not None else None

#     teleop_action_processor, robot_action_processor, robot_observation_processor = make_default_processors()

#     dataset_features = build_tm_dataset_features(robot)

#     # logging.info(f"[tm debug] robot.action_features = {robot.action_features}")
#     # logging.info(f"[tm debug] robot.observation_features = {robot.observation_features}")
#     # logging.info(f"[tm debug] dataset_features keys = {list(dataset_features.keys())}")

#     dataset = None
#     listener = None

#     try:
#         if cfg.resume:
#             dataset = LeRobotDataset(
#                 cfg.dataset.repo_id,
#                 root=cfg.dataset.root,
#                 batch_encoding_size=cfg.dataset.video_encoding_batch_size,
#                 vcodec=cfg.dataset.vcodec,
#             )

#             if hasattr(robot, "cameras") and len(robot.cameras) > 0:
#                 dataset.start_image_writer(
#                     num_processes=cfg.dataset.num_image_writer_processes,
#                     num_threads=cfg.dataset.num_image_writer_threads_per_camera * len(robot.cameras),
#                 )

#             sanity_check_dataset_robot_compatibility(dataset, robot, cfg.dataset.fps, dataset_features)

#         else:
#             sanity_check_dataset_name(cfg.dataset.repo_id, cfg.policy)
#             dataset = LeRobotDataset.create(
#                 cfg.dataset.repo_id,
#                 cfg.dataset.fps,
#                 root=cfg.dataset.root,
#                 robot_type=robot.name,
#                 features=dataset_features,
#                 use_videos=cfg.dataset.video,
#                 image_writer_processes=cfg.dataset.num_image_writer_processes,
#                 image_writer_threads=cfg.dataset.num_image_writer_threads_per_camera * len(robot.cameras),
#                 batch_encoding_size=cfg.dataset.video_encoding_batch_size,
#                 vcodec=cfg.dataset.vcodec,
#             )

#         policy = None if cfg.policy is None else make_policy(cfg.policy, ds_meta=dataset.meta)

#         preprocessor = None
#         postprocessor = None
#         if cfg.policy is not None:
#             preprocessor, postprocessor = make_pre_post_processors(
#                 policy_cfg=cfg.policy,
#                 pretrained_path=cfg.policy.pretrained_path,
#                 dataset_stats=rename_stats(dataset.meta.stats, cfg.dataset.rename_map),
#                 preprocessor_overrides={
#                     "device_processor": {"device": cfg.policy.device},
#                     "rename_observations_processor": {"rename_map": cfg.dataset.rename_map},
#                 },
#             )

#         robot.connect()
#         if teleop is not None:
#             teleop.connect()

#         listener, events = init_keyboard_listener()

#         with VideoEncodingManager(dataset):
#             recorded_episodes = 0
#             while recorded_episodes < cfg.dataset.num_episodes and not events["stop_recording"]:
#                 log_say(f"Recording episode {dataset.num_episodes}", cfg.play_sounds)

#                 if hasattr(robot, "reset"):
#                     robot.reset()
#                 precise_sleep(2.0)

#                 if teleop is not None and hasattr(teleop, "reset_for_new_episode"):
#                     teleop.reset_for_new_episode()

#                 record_loop(
#                     robot=robot,
#                     events=events,
#                     fps=cfg.dataset.fps,
#                     teleop_action_processor=teleop_action_processor,
#                     robot_action_processor=robot_action_processor,
#                     robot_observation_processor=robot_observation_processor,
#                     teleop=teleop,
#                     policy=policy,
#                     preprocessor=preprocessor,
#                     postprocessor=postprocessor,
#                     dataset=dataset,
#                     control_time_s=cfg.dataset.episode_time_s,
#                     single_task=cfg.dataset.single_task,
#                     display_data=cfg.display_data,
#                     display_compressed_images=display_compressed_images,
#                 )

#                 if not events["stop_recording"] and (
#                     (recorded_episodes < cfg.dataset.num_episodes - 1) or events["rerecord_episode"]
#                 ):
#                     log_say("Reset the environment", cfg.play_sounds)

#                     if hasattr(robot, "reset"):
#                         robot.reset()

#                     precise_sleep(cfg.dataset.reset_time_s)

#                 if events["rerecord_episode"]:
#                     log_say("Re-record episode", cfg.play_sounds)
#                     events["rerecord_episode"] = False
#                     events["exit_early"] = False
#                     dataset.clear_episode_buffer()
#                     continue

#                 dataset.save_episode()
#                 recorded_episodes += 1

#     finally:
#         log_say("Stop recording", cfg.play_sounds, blocking=True)

#         if dataset:
#             dataset.finalize()

#         if robot.is_connected:
#             robot.disconnect()
#         if teleop and teleop.is_connected:
#             teleop.disconnect()

#         if not is_headless() and listener:
#             listener.stop()

#         if cfg.dataset.push_to_hub:
#             dataset.push_to_hub(tags=cfg.dataset.tags, private=cfg.dataset.private)

#         log_say("Exiting", cfg.play_sounds)

#     return dataset


# def main():
#     register_third_party_plugins()
#     record()


# if __name__ == "__main__":
#     main()


import logging
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from pprint import pformat
from typing import Any

import numpy as np

from lerobot.cameras import (  # noqa: F401
    CameraConfig,  # noqa: F401
)
from lerobot.cameras.opencv.configuration_opencv import OpenCVCameraConfig  # noqa: F401
from lerobot.cameras.reachy2_camera.configuration_reachy2_camera import Reachy2CameraConfig  # noqa: F401
from lerobot.cameras.realsense.configuration_realsense import RealSenseCameraConfig  # noqa: F401
from lerobot.cameras.zmq.configuration_zmq import ZMQCameraConfig  # noqa: F401
from lerobot.configs import parser
from lerobot.configs.policies import PreTrainedConfig
from lerobot.datasets.image_writer import safe_stop_image_writer
from lerobot.datasets.lerobot_dataset import LeRobotDataset
from lerobot.datasets.utils import build_dataset_frame
from lerobot.datasets.video_utils import VideoEncodingManager
from lerobot.policies.factory import make_policy, make_pre_post_processors
from lerobot.policies.pretrained import PreTrainedPolicy
from lerobot.policies.utils import make_robot_action
from lerobot.robots.tm_follower import TMFollowerConfig, TMFollower
from lerobot.teleoperators.keyboard_xyz import KeyboardXYZTeleopConfig, KeyboardXYZTeleop
from lerobot.teleoperators.hand_gesture_xyz import HandGestureXYZTeleopConfig, HandGestureXYZTeleop
from lerobot.processor import (
    PolicyAction,
    PolicyProcessorPipeline,
    RobotAction,
    RobotObservation,
    RobotProcessorPipeline,
    make_default_processors,
)
from lerobot.processor.rename_processor import rename_stats
from lerobot.robots import (  # noqa: F401
    Robot,
    RobotConfig,
    bi_openarm_follower,
    bi_so_follower,
    earthrover_mini_plus,
    hope_jr,
    koch_follower,
    make_robot_from_config,
    omx_follower,
    openarm_follower,
    reachy2,
    so_follower,
    unitree_g1 as unitree_g1_robot,
)
from lerobot.teleoperators import (  # noqa: F401
    Teleoperator,
    TeleoperatorConfig,
    bi_openarm_leader,
    bi_so_leader,
    homunculus,
    koch_leader,
    make_teleoperator_from_config,
    omx_leader,
    openarm_leader,
    reachy2_teleoperator,
    so_leader,
    unitree_g1,
)
from lerobot.teleoperators.keyboard.teleop_keyboard import KeyboardTeleop
from lerobot.utils.constants import ACTION, OBS_STR
from lerobot.utils.control_utils import (
    init_keyboard_listener,
    is_headless,
    predict_action,
    sanity_check_dataset_name,
    sanity_check_dataset_robot_compatibility,
)
from lerobot.utils.import_utils import register_third_party_plugins
from lerobot.utils.robot_utils import precise_sleep
from lerobot.utils.utils import (
    get_safe_torch_device,
    init_logging,
    log_say,
)
from lerobot.utils.visualization_utils import init_rerun, log_rerun_data


# Dataset state/action semantics: 6 軸角 + 夾爪。
# Keyboard teleop may still output x/y/z/rx/ry/rz, but action saved to dataset is converted by robot.get_dataset_action().
STATE_NAMES = ["j1", "j2", "j3", "j4", "j5", "j6", "gripper"]


@dataclass
class DatasetRecordConfig:
    repo_id: str
    single_task: str
    root: str | Path | None = None
    fps: int = 10
    episode_time_s: int | float = 25
    reset_time_s: int | float = 1
    num_episodes: int = 50
    video: bool = True
    push_to_hub: bool = False
    private: bool = True
    tags: list[str] | None = None
    num_image_writer_processes: int = 8
    num_image_writer_threads_per_camera: int = 1
    video_encoding_batch_size: int = 1
    vcodec: str = "h264"
    rename_map: dict[str, str] = field(default_factory=dict)

    def __post_init__(self):
        if self.single_task is None:
            raise ValueError("You need to provide a task as argument in `single_task`.")


@dataclass
class RecordConfig:
    robot: RobotConfig
    dataset: DatasetRecordConfig
    teleop: TeleoperatorConfig | None = None
    policy: PreTrainedConfig | None = None
    display_data: bool = False
    display_ip: str | None = None
    display_port: int | None = None
    display_compressed_images: bool = False
    play_sounds: bool = True
    resume: bool = False

    def __post_init__(self):
        policy_path = parser.get_path_arg("policy")

        if policy_path:
            cli_overrides = parser.get_cli_overrides("policy")
            self.policy = PreTrainedConfig.from_pretrained(policy_path, cli_overrides=cli_overrides)
            self.policy.pretrained_path = policy_path

        if self.teleop is None and self.policy is None:
            raise ValueError("Choose a policy, a teleoperator or both to control the robot")

    @classmethod
    def __get_path_fields__(cls) -> list[str]:
        return ["policy"]


def build_tm_dataset_features(robot: Robot) -> dict[str, dict[str, Any]]:
    features: dict[str, dict[str, Any]] = {
        "action": {
            "dtype": "float32",
            "shape": (7,),
            "names": STATE_NAMES,
        },
        "observation.state": {
            "dtype": "float32",
            "shape": (7,),
            "names": STATE_NAMES,
        },
    }

    for cam_name in getattr(robot, "cameras", {}).keys():
        spec = robot.observation_features[cam_name]
        if not isinstance(spec, tuple) or len(spec) != 3:
            raise TypeError(f"Camera feature for {cam_name} should be (H, W, 3), got {spec}")
        features[f"observation.images.{cam_name}"] = {
            "dtype": "video",
            "shape": spec,
            "names": ["height", "width", "channel"],
        }

    return features


def vec_to_named_dict(vec: np.ndarray) -> dict[str, float]:
    arr = np.asarray(vec, dtype=np.float32)
    if arr.shape != (len(STATE_NAMES),):
        raise ValueError(f"Expected shape ({len(STATE_NAMES)},), got {arr.shape}")
    return {name: float(arr[i]) for i, name in enumerate(STATE_NAMES)}


def _extract_tm_state(obs_like: Any) -> np.ndarray:
    if isinstance(obs_like, dict):
        if "state" in obs_like:
            state_val = obs_like["state"]
            if isinstance(state_val, dict):
                arr = np.asarray([state_val[k] for k in STATE_NAMES], dtype=np.float32)
            else:
                arr = np.asarray(state_val, dtype=np.float32)
        elif all(k in obs_like for k in STATE_NAMES):
            arr = np.asarray([obs_like[k] for k in STATE_NAMES], dtype=np.float32)
        elif all(f"observation.{k}" in obs_like for k in STATE_NAMES):
            arr = np.asarray([obs_like[f"observation.{k}"] for k in STATE_NAMES], dtype=np.float32)
        else:
            raise KeyError(f"Cannot extract TM state from keys: {list(obs_like.keys())}")
    else:
        arr = np.asarray(obs_like, dtype=np.float32)

    if arr.shape != (len(STATE_NAMES),):
        raise ValueError(f"TM state must have shape ({len(STATE_NAMES)},), got {arr.shape}")
    return arr.astype(np.float32)


def _is_joint_action_like(action_like: Any) -> bool:
    """
    keyboard z flow 可能直接輸出 {action: {j1..j6, gripper}}。
    這種 action 不要再丟進以 TCP feature 為主的 teleop processor，
    直接交給 robot.send_action()，robot 端會用 JPP 執行。
    """
    if not isinstance(action_like, dict):
        return False

    a = action_like.get("action", action_like)
    if isinstance(a, dict):
        if all(k in a for k in STATE_NAMES):
            return True
        if all(f"action.{k}" in a for k in STATE_NAMES):
            return True
    return False


def _extract_tm_images(obs_processed: Any, obs_raw: Any, robot: Robot) -> dict[str, Any]:
    required = list(getattr(robot, "cameras", {}).keys())
    if not required:
        return {}

    candidates = []
    if isinstance(obs_processed, dict):
        candidates.extend([
            obs_processed.get("observation.images", None),
            obs_processed.get("obs.images", None),
        ])
    if isinstance(obs_raw, dict):
        candidates.extend([
            obs_raw.get("observation.images", None),
            obs_raw.get("obs.images", None),
        ])

    for cand in candidates:
        if isinstance(cand, dict) and all(k in cand and cand[k] is not None for k in required):
            return {k: cand[k] for k in required}

    out = {}
    srcs = []
    if isinstance(obs_processed, dict):
        srcs.append(obs_processed)
    if isinstance(obs_raw, dict):
        srcs.append(obs_raw)

    for k in required:
        found = None
        for src in srcs:
            if k in src and src[k] is not None:
                found = src[k]
                break
        if found is None:
            raise ValueError(f"Missing frame for required camera '{k}'")
        out[k] = found

    return out


def normalize_tm_observation_for_dataset(
    obs_raw: RobotObservation,
    obs_processed: RobotObservation,
    robot: Robot,
) -> dict[str, Any]:
    state_vec = _extract_tm_state(obs_processed if obs_processed is not None else obs_raw)
    state_named = vec_to_named_dict(state_vec)
    images = _extract_tm_images(obs_processed, obs_raw, robot)

    out = dict(state_named)

    if images:
        out["observation.images"] = images
        out["obs.images"] = images
        for k, v in images.items():
            out[k] = v

    return out


def _extract_tm_action_vector(action_like: Any) -> np.ndarray:
    if isinstance(action_like, dict):
        if "action" in action_like:
            a = action_like["action"]
            if isinstance(a, dict):
                if not all(k in a for k in STATE_NAMES):
                    raise KeyError(f"Action dict missing keys. Got: {list(a.keys())}")
                arr = np.asarray([a[k] for k in STATE_NAMES], dtype=np.float32)
            else:
                arr = np.asarray(a, dtype=np.float32)
        elif all(k in action_like for k in STATE_NAMES):
            arr = np.asarray([action_like[k] for k in STATE_NAMES], dtype=np.float32)
        elif all(f"action.{k}" in action_like for k in STATE_NAMES):
            arr = np.asarray([action_like[f"action.{k}"] for k in STATE_NAMES], dtype=np.float32)
        else:
            raise KeyError(f"Cannot extract TM action from keys: {list(action_like.keys())}")
    else:
        arr = np.asarray(action_like, dtype=np.float32)

    if arr.shape != (len(STATE_NAMES),):
        raise ValueError(f"TM action must have shape ({len(STATE_NAMES)},), got {arr.shape}")
    return arr.astype(np.float32)


@safe_stop_image_writer
def record_loop(
    robot: Robot,
    events: dict,
    fps: int,
    teleop_action_processor: RobotProcessorPipeline[
        tuple[RobotAction, RobotObservation], RobotAction
    ],
    robot_action_processor: RobotProcessorPipeline[
        tuple[RobotAction, RobotObservation], RobotAction
    ],
    robot_observation_processor: RobotProcessorPipeline[
        RobotObservation, RobotObservation
    ],
    dataset: LeRobotDataset | None = None,
    teleop: Teleoperator | list[Teleoperator] | None = None,
    policy: PreTrainedPolicy | None = None,
    preprocessor: PolicyProcessorPipeline[dict[str, Any], dict[str, Any]] | None = None,
    postprocessor: PolicyProcessorPipeline[PolicyAction, PolicyAction] | None = None,
    control_time_s: int | None = None,
    single_task: str | None = None,
    display_data: bool = False,
    display_compressed_images: bool = False,
):
    if dataset is not None and dataset.fps != fps:
        raise ValueError(f"The dataset fps should be equal to requested fps ({dataset.fps} != {fps}).")

    teleop_arm = teleop_keyboard = None
    if isinstance(teleop, list):
        teleop_keyboard = next((t for t in teleop if isinstance(t, KeyboardTeleop)), None)
        teleop_arm = next(
            (
                t
                for t in teleop
                if isinstance(
                    t,
                    (
                        so_leader.SO100Leader
                        | so_leader.SO101Leader
                        | koch_leader.KochLeader
                        | omx_leader.OmxLeader
                    ),
                )
            ),
            None,
        )

        if not (teleop_arm and teleop_keyboard and len(teleop) == 2 and robot.name == "lekiwi_client"):
            raise ValueError(
                "For multi-teleop, the list must contain exactly one KeyboardTeleop and one arm teleoperator. Currently only supported for LeKiwi robot."
            )

    if policy is not None and preprocessor is not None and postprocessor is not None:
        policy.reset()
        preprocessor.reset()
        postprocessor.reset()

    timestamp = 0
    start_episode_t = time.perf_counter()

    while timestamp < control_time_s:
        start_loop_t = time.perf_counter()

        if events["exit_early"]:
            events["exit_early"] = False
            break

        obs = robot.get_observation()
        obs_processed = robot_observation_processor(obs)

        tm_obs_for_dataset = normalize_tm_observation_for_dataset(obs, obs_processed, robot)
        if not hasattr(record_loop, "_dbg_obs_once"):
            record_loop._dbg_obs_once = True
            # logging.info(f"[tm debug] tm_obs_for_dataset keys = {list(tm_obs_for_dataset.keys())}")
            # logging.info(
            #     f"[tm debug] tm_obs_for_dataset[state] = "
            #     f"{ {k: tm_obs_for_dataset[k] for k in STATE_NAMES if k in tm_obs_for_dataset} }"
            # )

        observation_frame = None

        if policy is not None or dataset is not None:
            observation_frame = build_dataset_frame(dataset.features, tm_obs_for_dataset, prefix=OBS_STR)

        if policy is not None and preprocessor is not None and postprocessor is not None:
            action_values = predict_action(
                observation=observation_frame,
                policy=policy,
                device=get_safe_torch_device(policy.config.device),
                preprocessor=preprocessor,
                postprocessor=postprocessor,
                use_amp=policy.config.use_amp,
                task=single_task,
                robot_type=robot.robot_type,
            )
            act_processed_policy: RobotAction = make_robot_action(action_values, dataset.features)
#####
        elif policy is None and isinstance(teleop, Teleoperator):
            if hasattr(robot, "get_teleop_feedback") and hasattr(teleop, "send_feedback"):
                teleop.send_feedback(robot.get_teleop_feedback())

            act = teleop.get_action()
            if _is_joint_action_like(act):
                # z 自動流程已經輸出 j1~j6，不再用 TCP teleop processor 處理。
                act_processed_teleop = act
            else:
                act_processed_teleop = teleop_action_processor((act, obs))
######
        elif policy is None and isinstance(teleop, list):
            arm_action = teleop_arm.get_action()
            arm_action = {f"arm_{k}": v for k, v in arm_action.items()}
            keyboard_action = teleop_keyboard.get_action()
            base_action = robot._from_keyboard_to_base_action(keyboard_action)
            act = {**arm_action, **base_action} if len(base_action) > 0 else arm_action
            act_processed_teleop = teleop_action_processor((act, obs))
        else:
            logging.info(
                "No policy or teleoperator provided, skipping action generation."
                "This is likely to happen when resetting the environment without a teleop device."
                "The robot won't be at its rest position at the start of the next episode."
            )
            continue

        if policy is not None and act_processed_policy is not None:
            action_values = act_processed_policy
            robot_action_to_send = robot_action_processor((act_processed_policy, obs))
        else:
            action_values = act_processed_teleop
            if _is_joint_action_like(act_processed_teleop):
                # joint action 直接交給 robot，避免 processor 用 TCP feature 名稱重包裝。
                robot_action_to_send = act_processed_teleop
            else:
                robot_action_to_send = robot_action_processor((act_processed_teleop, obs))

        _sent_action = robot.send_action(robot_action_to_send)

        # Dataset action 統一記錄為 [j1, j2, j3, j4, j5, j6, gripper]。
        # teleop 控制時，action_values 仍是 TCP；robot.send_action() 送出 TCP 後，
        # robot.get_dataset_action() 會回傳當下/最近的 joint feedback 作為 action。
        if hasattr(robot, "get_dataset_action"):
            tm_action_vec = np.asarray(robot.get_dataset_action(), dtype=np.float32)
        else:
            tm_action_vec = _extract_tm_action_vector(action_values)
        tm_action_named = vec_to_named_dict(tm_action_vec)

        if not hasattr(record_loop, "_dbg_act_once"):
            record_loop._dbg_act_once = True
            # logging.info(f"[tm debug] tm_action_named = {tm_action_named}")

        if dataset is not None:
            action_frame = build_dataset_frame(dataset.features, tm_action_named, prefix=ACTION)
            frame = {**observation_frame, **action_frame, "task": single_task}
            # print(
            #     f"action.gripper={tm_action_named['gripper']}, "
            #     f"obs.gripper={tm_obs_for_dataset['gripper']}"
            # )
            dataset.add_frame(frame)

        if display_data:
            log_rerun_data(
                observation=tm_obs_for_dataset,
                action=tm_action_vec,
                compress_images=display_compressed_images,
            )

        dt_s = time.perf_counter() - start_loop_t
        precise_sleep(max(1 / fps - dt_s, 0.0))
        timestamp = time.perf_counter() - start_episode_t


@parser.wrap()
def record(cfg: RecordConfig) -> LeRobotDataset:
    init_logging()
    logging.info(pformat(asdict(cfg)))

    if cfg.display_data:
        init_rerun(session_name="recording", ip=cfg.display_ip, port=cfg.display_port)

    display_compressed_images = (
        True
        if (cfg.display_data and cfg.display_ip is not None and cfg.display_port is not None)
        else cfg.display_compressed_images
    )

    robot = make_robot_from_config(cfg.robot)
    teleop = make_teleoperator_from_config(cfg.teleop) if cfg.teleop is not None else None

    teleop_action_processor, robot_action_processor, robot_observation_processor = make_default_processors()

    dataset_features = build_tm_dataset_features(robot)

    # logging.info(f"[tm debug] robot.action_features = {robot.action_features}")
    # logging.info(f"[tm debug] robot.observation_features = {robot.observation_features}")
    # logging.info(f"[tm debug] dataset_features keys = {list(dataset_features.keys())}")

    dataset = None
    listener = None

    try:
        if cfg.resume:
            dataset = LeRobotDataset(
                cfg.dataset.repo_id,
                root=cfg.dataset.root,
                batch_encoding_size=cfg.dataset.video_encoding_batch_size,
                vcodec=cfg.dataset.vcodec,
            )

            if hasattr(robot, "cameras") and len(robot.cameras) > 0:
                dataset.start_image_writer(
                    num_processes=cfg.dataset.num_image_writer_processes,
                    num_threads=cfg.dataset.num_image_writer_threads_per_camera * len(robot.cameras),
                )

            sanity_check_dataset_robot_compatibility(dataset, robot, cfg.dataset.fps, dataset_features)

        else:
            sanity_check_dataset_name(cfg.dataset.repo_id, cfg.policy)
            dataset = LeRobotDataset.create(
                cfg.dataset.repo_id,
                cfg.dataset.fps,
                root=cfg.dataset.root,
                robot_type=robot.name,
                features=dataset_features,
                use_videos=cfg.dataset.video,
                image_writer_processes=cfg.dataset.num_image_writer_processes,
                image_writer_threads=cfg.dataset.num_image_writer_threads_per_camera * len(robot.cameras),
                batch_encoding_size=cfg.dataset.video_encoding_batch_size,
                vcodec=cfg.dataset.vcodec,
            )

        policy = None if cfg.policy is None else make_policy(cfg.policy, ds_meta=dataset.meta)

        preprocessor = None
        postprocessor = None
        if cfg.policy is not None:
            preprocessor, postprocessor = make_pre_post_processors(
                policy_cfg=cfg.policy,
                pretrained_path=cfg.policy.pretrained_path,
                dataset_stats=rename_stats(dataset.meta.stats, cfg.dataset.rename_map),
                preprocessor_overrides={
                    "device_processor": {"device": cfg.policy.device},
                    "rename_observations_processor": {"rename_map": cfg.dataset.rename_map},
                },
            )

        robot.connect()
        if teleop is not None:
            teleop.connect()

        listener, events = init_keyboard_listener()

        with VideoEncodingManager(dataset):
            recorded_episodes = 0
            while recorded_episodes < cfg.dataset.num_episodes and not events["stop_recording"]:
                log_say(f"Recording episode {dataset.num_episodes}", cfg.play_sounds)

                if hasattr(robot, "reset"):
                    robot.reset()
                precise_sleep(2.0)

                if teleop is not None and hasattr(teleop, "reset_for_new_episode"):
                    teleop.reset_for_new_episode()

                record_loop(
                    robot=robot,
                    events=events,
                    fps=cfg.dataset.fps,
                    teleop_action_processor=teleop_action_processor,
                    robot_action_processor=robot_action_processor,
                    robot_observation_processor=robot_observation_processor,
                    teleop=teleop,
                    policy=policy,
                    preprocessor=preprocessor,
                    postprocessor=postprocessor,
                    dataset=dataset,
                    control_time_s=cfg.dataset.episode_time_s,
                    single_task=cfg.dataset.single_task,
                    display_data=cfg.display_data,
                    display_compressed_images=display_compressed_images,
                )

                if not events["stop_recording"] and (
                    (recorded_episodes < cfg.dataset.num_episodes - 1) or events["rerecord_episode"]
                ):
                    log_say("Reset the environment", cfg.play_sounds)

                    if hasattr(robot, "reset"):
                        robot.reset()

                    precise_sleep(cfg.dataset.reset_time_s)

                if events["rerecord_episode"]:
                    log_say("Re-record episode", cfg.play_sounds)
                    events["rerecord_episode"] = False
                    events["exit_early"] = False
                    dataset.clear_episode_buffer()
                    continue

                dataset.save_episode()
                recorded_episodes += 1

    finally:
        log_say("Stop recording", cfg.play_sounds, blocking=True)

        if dataset:
            dataset.finalize()

        if robot.is_connected:
            robot.disconnect()
        if teleop and teleop.is_connected:
            teleop.disconnect()

        if not is_headless() and listener:
            listener.stop()

        if cfg.dataset.push_to_hub:
            dataset.push_to_hub(tags=cfg.dataset.tags, private=cfg.dataset.private)

        log_say("Exiting", cfg.play_sounds)

    return dataset


def main():
    register_third_party_plugins()
    record()


if __name__ == "__main__":
    main()