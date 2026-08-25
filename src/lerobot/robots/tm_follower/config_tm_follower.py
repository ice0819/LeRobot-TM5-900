from dataclasses import dataclass, field

from lerobot.cameras import CameraConfig
from lerobot.robots.config import RobotConfig


@RobotConfig.register_subclass("tm_follower")
@dataclass
class TMFollowerConfig(RobotConfig):
    type: str = "tm_follower"

    tool_pose_topic: str = "/tool_pose"
    send_script_service: str = "/send_script"

    cameras: dict[str, CameraConfig] = field(default_factory=dict)