import csv
import re
import numpy as np
import tensorflow as tf
import os
import glob

import matplotlib.pyplot as plt
import matplotlib
import sys
from Controllers.controller_grad_cem import q as stage_cost
# from PyQt5.QtCore import *
# from PyQt5.QtGui import *
# from PyQt5.QtWidgets import *
matplotlib.use('Qt5Agg')


from CartPole.cartpole_model import TrackHalfLength
from CartPole.state_utilities import (
    ANGLE_COS_IDX,
    ANGLE_IDX,
    ANGLED_IDX,
    ANGLE_SIN_IDX,
    POSITION_IDX,
    POSITIOND_IDX,
    STATE_VARIABLES,
    STATE_INDICES,
    create_cartpole_state,
)

exp_length_idx = 0
sim_dt_idx = 1
cont_dt_idx = 2
saving_dt_idx = 3
controller_idx = 4

m_param_idx = 5
M_param_idx = 6
L_param_idx = 7
u_max_param_idx = 8
M_fric_parm_idx = 9
J_fric_param_idx = 10
v_max_idx = 11
TrackHalfLength_idx = 12
contDist_idx = 13
contBias_idx = 14
g_param_idx = 15
k_param_idx = 16


def data_idx(list):
    ds = re.compile('# Data:')
    for i in range(len(list)):
        if ds.match(list[i][0]):
            return i
    return -1


# %% extract all data from all experiments

path = 'Experiment_Recordings/Experiment-[0-9]*.csv'
files = glob.glob(path)

all_data = []

for file in files:
    lines = []
    with open(file, mode='r') as file_read:
        csvFile = csv.reader(file_read)
        for line in csvFile:
            if line:
                lines.append(line)
    ds = data_idx(lines) + 1
    all_data.append(lines[ds + 1:])

beginning = re.compile('#.*:\s*')
second = re.compile('\s*s\Z')
exp_info = []
with_s_idx = [3, 6, 7, 8]
for idx in with_s_idx:
    truncated = beginning.sub('', second.sub('', lines[idx][0]))
    if not truncated:
        exp_info.append(None)
    else:
        exp_info.append(float(truncated))
controller = beginning.sub('', second.sub('', lines[10][0]))
exp_info.append(controller)
param_idx = [13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24]
for idx in param_idx:
    exp_info.append(float(beginning.sub('', lines[idx][0])))

data_legend = lines[ds]
time_idx = data_legend.index('time')
position_idx = data_legend.index('position')
angle_idx = data_legend.index('angle')
u_idx = data_legend.index('u')
Q_idx = data_legend.index('Q')
angle_cos_idx = data_legend.index('angle_cos')
angle_sin_idx = data_legend.index('angle_sin')
angleD_idx = data_legend.index('angleD')
positionD_idx = data_legend.index('positionD')
target_pos_idx = data_legend.index('target_position')

all_data = np.float32(all_data)


#%% Test stage cost
S = np.empty(shape = (all_data.shape[0], all_data.shape[1], 6))
S[..., ANGLE_COS_IDX] = all_data[..., angle_cos_idx]
S[..., ANGLE_SIN_IDX] = all_data[..., angle_sin_idx]
S[..., POSITION_IDX] = all_data[..., position_idx]
S[..., ANGLE_IDX] = all_data[..., angle_idx]
S[..., POSITIOND_IDX] = all_data[..., positionD_idx]
S[..., ANGLED_IDX] = all_data[..., angleD_idx]

target_pos = tf.constant(all_data[..., target_pos_idx], dtype=tf.float32)

Q = all_data[..., Q_idx]

Q = tf.constant(Q, dtype= tf.float32)
S = tf.constant(S, dtype= tf.float32)
num_rol = all_data.shape[0]
costs = stage_cost(S, Q, target_pos, Q[0,0], nrol=num_rol)
filter = tf.ones([10,1,1], dtype=tf.float32)

#%%

running_avg = tf.squeeze(tf.nn.conv1d(costs[:, :, tf.newaxis], filter, 1, 'SAME', data_format = "NWC"))/filter.shape[0]









#%%

data = all_data[0]

fig, ax1 = plt.subplots(5,1,num='yoyoyo')
ax1 = plt.subplot(5, 1, 1)
plt.plot(data[:, time_idx], data[:, angle_idx])
plt.ylim(-np.pi,np.pi)


ax1 = plt.subplot(5, 1, 2)
plt.plot(data[:, time_idx], data[:, position_idx])
plt.ylim(-exp_info[TrackHalfLength_idx], exp_info[TrackHalfLength_idx])

ax1 = plt.subplot(5, 1, 3)
plt.plot(data[:, time_idx], data[:, u_idx])
plt.ylim(-exp_info[u_max_param_idx], exp_info[u_max_param_idx])

plt.subplot(5,1,4)
plt.semilogy(data[:, time_idx], costs[0,:])

plt.subplot(5, 1, 5)
plt.semilogy(data[:, time_idx], running_avg[0,:])

plt.show()

