"""RclpyTransport: the real ROS2 side of the RosTransport interface.

Design: the node is dependency-injected, so all encode/decode + latest-message-cache
logic is testable with a fake node and no rclpy. Per-topic codecs (encode/decode
callables) map between the engine's neutral JointCommand/JointState dataclasses and
the concrete AimDK message types — fill those in from your bridge's msg definitions.

Only `create()` imports rclpy and starts the background executor spin thread.
"""
from __future__ import annotations

from typing import Callable

DEFAULT_QOS = 10  # rclpy accepts an int depth as a QoS profile


class RclpyTransport:
    def __init__(self, node, qos: int = DEFAULT_QOS):
        self._node = node
        self._qos = qos
        self._publishers: dict[str, object] = {}
        self._pub_msg_types: dict[str, object] = {}
        self._encoders: dict[str, Callable] = {}
        self._decoders: dict[str, Callable] = {}
        self._latest: dict[str, object] = {}

    def register_publisher(self, topic: str, msg_type, encode: Callable) -> None:
        self._publishers[topic] = self._node.create_publisher(msg_type, topic, self._qos)
        self._pub_msg_types[topic] = msg_type
        self._encoders[topic] = encode

    def register_subscription(self, topic: str, msg_type, decode: Callable) -> None:
        self._decoders[topic] = decode
        self._node.create_subscription(
            msg_type, topic, lambda m, t=topic: self._on_msg(t, m), self._qos)

    def _on_msg(self, topic: str, ros_msg) -> None:
        self._latest[topic] = ros_msg

    # ---- RosTransport interface ----
    def publish(self, topic: str, msg) -> None:
        ros_msg = self._encoders[topic](msg, self._pub_msg_types[topic])
        self._publishers[topic].publish(ros_msg)

    def latest(self, topic: str):
        ros_msg = self._latest.get(topic)
        if ros_msg is None:
            return None
        return self._decoders[topic](ros_msg)

    # ---- guarded factory: the only rclpy-touching code ----
    @classmethod
    def create(cls, node_name: str = "aspire_robot_engine", qos: int = DEFAULT_QOS):
        try:
            import rclpy
            from rclpy.node import Node
        except ImportError as e:  # pragma: no cover - environment without ROS2
            raise RuntimeError(
                "rclpy is not available. Install ROS2 (and source the overlay) to use "
                "RclpyTransport, or use FakeRosTransport for hardware-free runs."
            ) from e

        import threading

        if not rclpy.ok():
            rclpy.init()
        node = Node(node_name)
        executor = rclpy.executors.SingleThreadedExecutor()
        executor.add_node(node)
        threading.Thread(target=executor.spin, daemon=True).start()
        return cls(node, qos=qos)
