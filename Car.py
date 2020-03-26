from random import random
import math
import numpy as np
from PIL import Image


# constants
b = 1.2  # in m, distance from CG to front axle
c = 1.8  # in m, distance from CG to rear axle
wheelbase = b + c  # in m, distance between axles
h = 0.25  # in m, height of CG from ground
front_wing = 1.1  # in m, distance from front axle to front of the car
rear_wing = 0.7  # in m, distance from rear axle to rear of the car
mass = 750.  # in kg
length = wheelbase + front_wing + rear_wing  # in m
width = 1.8  # in m
inertia = mass*(h**2+length**2)/12  # in kg.m**2
wheel_radius = 0.4  # in m
drag = 0.4  # constant for drag resistance
rr = 30 * drag  # constant for rolling resistance
ca_r = -5.2  # cornering stiffness for rear wheels
ca_f = -5.  # cornering stiffness for front wheels
tyre_grip = 2.5  # diameter of friction circle
braking_constant = 13000.
gear_ratios = [2.66, 1.78, 1.3, 1., 0.74, 0.5]
differential_ratio = 3.42
g = 9.81
scale = 5.

# precalculated values
h_L = h / wheelbase
b_L = b / wheelbase
c_L = c / wheelbase
front_cg = b+front_wing * scale
side_cg = width/2 * scale
final_ratios = [differential_ratio * i for i in gear_ratios]
a_rpm = -17/1015000
b_rpm = 2363/20300
c_rpm = 8596/29

transmission_efficiency = 0.8
rad_to_rpm = 30 / (math.pi * wheel_radius)
track = np.array(Image.open('test_track.jpg').transpose(Image.FLIP_TOP_BOTTOM))


def rpm_to_torque(rpm):
    return max(((a_rpm * rpm + b_rpm) * rpm + c_rpm), 1000)


class Car:
    anch_x = int((rear_wing + c) * scale)
    anch_y = int(width * scale / 2)

    def __init__(self, network=None):
        self.pos_x = 800.
        self.pos_y = 450.
        self.rot_rad = math.radians(0)
        self.sin_rotation = math.sin(self.rot_rad)
        self.cos_rotation = math.cos(self.rot_rad)
        self.steering = 0.
        self.wheel_position = 0.
        self.acceleration_pedal = 0.
        self.braking_pedal = 0.
        self.gear = 0
        self.rpm = 1000.
        self.acceleration_last = 0
        self.velocity_x = 0.
        self.velocity_y = 0.
        self.velocity_local_x = 0.
        self.velocity_local_y = 0.
        self.velocity_angular = 0.
        self.fuel = 100.
        self.score = 0.
        self.distance = 0.
        self.alive_counter = 0
        self.alive = True
        self.death_counter = 0
        self.avg_acc = 0.
        self.avg_brk = 0.
        self.avg_fc = 0.
        self.avg_dis = 0.
        self.max_lateral = 0.
        if network is None:
            self.network = []
            layers = (8, 6, 3)
            for i in range(len(layers) - 1):
                weights = []
                bias = []
                for j in range(layers[i + 1]):
                    row = []
                    for k in range(layers[i]):
                        row.append(random() * 2 - 1)
                    bias.append(len(row)*(random() * 2 - 1))
                    weights.append(row)
                self.network.append((weights, bias))
        else:
            self.network = network

    def update_car(self, dt=0.01):
        if not self.alive:
            return
        self.alive_counter += 1

        if abs(self.steering) > 0.001:
            self.wheel_position = min(max(self.wheel_position + self.steering * dt * 2.0, -1.0), 1.0)
        else:
            if self.wheel_position > 0:
                self.wheel_position = max(self.wheel_position - dt * 1.0, 0)
            elif self.wheel_position < 0:
                self.wheel_position = min(self.wheel_position + dt * 1.0, 0)

        # collision detection
        front_x = self.pos_x + self.cos_rotation * front_cg
        front_y = self.pos_y - self.sin_rotation * front_cg
        left_x = front_x + self.sin_rotation * side_cg
        left_y = front_y + self.cos_rotation * side_cg
        right_x = front_x - self.sin_rotation * side_cg
        right_y = front_y - self.cos_rotation * side_cg
        if track[int(left_y)][int(left_x)] > 20 or track[int(right_y)][int(right_x)] > 20:
            self.score = self.distance * 0.01 - 0.001 * self.alive_counter
            self.alive = False
            return

        # transforming velocity from global to local coordinates
        self.velocity_local_x = self.cos_rotation * self.velocity_x - self.sin_rotation * self.velocity_y
        self.velocity_local_y = self.cos_rotation * self.velocity_y + self.sin_rotation * self.velocity_x
        steering_angle = 0.38 * self.steering  # angle in range -0.38 to 0.38 rad

        # Weight on wheels
        car_mass = mass + self.fuel
        car_weight = car_mass * g
        weight_transfer = h_L * car_mass * self.acceleration_last
        weight_front = c_L * car_weight - weight_transfer
        weight_rear = b_L * car_weight + weight_transfer

        # Steering forces
        yaw_speed_front = b * self.velocity_angular
        yaw_speed_rear = c * self.velocity_angular
        alpha_front = math.atan2(self.velocity_local_y + yaw_speed_front, abs(self.velocity_local_x)) - np.sign(
            self.velocity_local_x) * steering_angle
        alpha_rear = math.atan2(self.velocity_local_y - yaw_speed_rear, abs(self.velocity_local_x))
        tg = tyre_grip + self.velocity_local_x / 10.  # downforce
        force_lateral_front = min(max(ca_f * alpha_front, -tg), tg) * weight_front
        force_lateral_rear = min(max(ca_f * alpha_rear, -tg), tg) * weight_rear
        force_lat = force_lateral_front * math.cos(steering_angle) + force_lateral_rear
        self.max_lateral = max(force_lat, self.max_lateral)

        # traction force from engine and brakes
        self.rpm = self.velocity_local_x * final_ratios[self.gear] * rad_to_rpm
        torque_engine = rpm_to_torque(self.rpm) * self.acceleration_pedal
        force_drive = torque_engine * final_ratios[self.gear] * transmission_efficiency / wheel_radius
        force_brake = braking_constant * self.braking_pedal
        self.fuel -= dt * torque_engine / 100000
        force_traction = force_drive - force_brake * np.sign(self.velocity_local_x)
        force_resistance = (drag * self.velocity_local_x + rr) * self.velocity_local_x
        force_long = force_traction - force_resistance

        acceleration_local_x = force_long / car_mass
        acceleration_local_y = force_lat / car_mass
        self.acceleration_last = acceleration_local_x
        acceleration_x = self.cos_rotation * acceleration_local_x + self.sin_rotation * acceleration_local_y
        acceleration_y = -self.sin_rotation * acceleration_local_x + self.cos_rotation * acceleration_local_y
        self.velocity_x += dt * acceleration_x
        self.velocity_y += dt * acceleration_y

        angular_torque = force_lateral_front * b - force_lateral_rear * c

        speed = (self.velocity_x ** 2 + self.velocity_y ** 2) ** 0.5
        self.distance += dt*speed
        if self.distance > 10000:
            self.score = self.distance * 0.01 - 0.001 * self.alive_counter
            self.alive = False
            return
        if speed < 0.5 and self.acceleration_pedal == 0:
            self.velocity_x = 0
            self.velocity_y = 0
            angular_torque = 0
            self.velocity_angular = 0
            self.death_counter += 1
        elif speed < 10:
            self.death_counter += 1
            if self.death_counter >= 500:
                self.score = self.distance * 0.01 - 0.001 * self.alive_counter
                self.alive = False
                return

        acceleration_angular = angular_torque / inertia
        self.velocity_angular += dt * acceleration_angular

        if self.velocity_angular != 0:
            self.rot_rad += dt * self.velocity_angular
            self.sin_rotation = math.sin(self.rot_rad)
            self.cos_rotation = math.cos(self.rot_rad)

        self.pos_x += scale * dt * self.velocity_x
        self.pos_y += scale * dt * self.velocity_y

    def think(self):
        cos_30 = math.cos(self.rot_rad + math.radians(30))
        sin_30 = math.sin(self.rot_rad + math.radians(30))
        cos_60 = math.cos(self.rot_rad + math.radians(60))
        sin_60 = math.sin(self.rot_rad + math.radians(60))
        sensor_m60 = self.sensor(-cos_30, sin_30)
        sensor_60 = self.sensor(sin_60, cos_60)
        self.avg_dis += sensor_60 - sensor_m60
        inputs = [self.velocity_local_x/65.234, self.velocity_local_y/30., self.velocity_angular, sensor_m60, self.sensor(-cos_60, sin_60),
                  self.sensor(self.sin_rotation, self.cos_rotation), self.sensor(sin_30, cos_30), sensor_60]
        outputs = []
        for layer in self.network:
            outputs.clear()
            for i in range(len(layer[1])):
                val = layer[1][i]
                for j in range(len(layer[0][i])):
                    val += layer[0][i][j] * inputs[j]
                outputs.append(math.tanh(val))
            inputs = outputs.copy()
        self.acceleration_pedal = (outputs[0] + 1) / 2
        self.avg_acc += self.acceleration_pedal
        self.braking_pedal = (outputs[1] + 1) / 2
        self.avg_brk += self.braking_pedal
        self.steering = outputs[2]
        if self.rpm > 5500:
            self.gear += 1
            self.gear = min(5, self.gear)
        if self.rpm < 2000:
            self.gear -= 1
            self.gear = max(0, self.gear)

    def sensor(self, sin, cos):
        for i in range(0, int(250 * scale), int(scale)):
            if track[int(self.pos_y - i * sin)][int(self.pos_x + i * cos)] > 20:
                return (i / scale / 250 - 1)**3+1
        return 1

    def copy(self):
        from copy import deepcopy
        return Car(deepcopy(self.network))