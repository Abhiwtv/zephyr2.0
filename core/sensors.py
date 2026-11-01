"""
Bridge exports for symbolic sensors to support both import styles:
1. from core.sensors import InfrastructureSensor, TrafficSensor, L4L7Sensor
2. from agents.<domain>.sensor import <Domain>Sensor
"""

from agents.infrastructure.sensor import InfrastructureSensor
from agents.traffic.sensor import TrafficSensor
from agents.l4_l7.sensor import L4L7Sensor

__all__ = ["InfrastructureSensor", "TrafficSensor", "L4L7Sensor"]
