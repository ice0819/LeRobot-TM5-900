from dataclasses import dataclass
from lerobot.teleoperators.config import TeleoperatorConfig


@TeleoperatorConfig.register_subclass("keyboard_xyz")
@dataclass
class KeyboardXYZTeleopConfig(TeleoperatorConfig):
    type: str = "keyboard_xyz"
    pos_step: float =5.0
    rot_step: float =2.5