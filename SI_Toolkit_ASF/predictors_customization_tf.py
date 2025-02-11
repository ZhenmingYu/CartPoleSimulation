from typing import Callable, Optional
import tensorflow as tf
from CartPole.cartpole_model_tf import Q2u

from CartPole.state_utilities import STATE_INDICES, STATE_VARIABLES, CONTROL_INPUTS, CONTROL_INDICES, create_cartpole_state
from CartPole.state_utilities import ANGLE_IDX, ANGLED_IDX, POSITION_IDX, POSITIOND_IDX, ANGLE_COS_IDX, ANGLE_SIN_IDX

from CartPole.cartpole_tf import cartpole_fine_integration_tf, Q2u_tf
from CartPole.cartpole_model import L

from SI_Toolkit.Functions.TF.Compile import CompileTF, CompileAdaptive

STATE_INDICES_TF = tf.lookup.StaticHashTable(
    initializer=tf.lookup.KeyValueTensorInitializer(
        keys=tf.constant(list(STATE_INDICES.keys())), values=tf.constant(list(STATE_INDICES.values()))),
    default_value=-100, name=None
)


class next_state_predictor_ODE_tf():

    def __init__(self,
                 dt,
                 intermediate_steps,
                 batch_size=1,
                 variable_parameters=None,
                 disable_individual_compilation=False):
        self.intermediate_steps = tf.convert_to_tensor(intermediate_steps, dtype=tf.int32)
        self.t_step = tf.convert_to_tensor(dt / float(self.intermediate_steps), dtype=tf.float32)

        self.variable_parameters = variable_parameters

        if disable_individual_compilation:
            self.step = self._step
        else:
            self.step = CompileTF(self._step)

    def _step(self, s, Q):

        # assert does not work with CompileTF, but left here for information
        # assert Q.shape[0] == s.shape[0]
        # assert Q.ndim == 2
        # assert s.ndim == 2

        if self.variable_parameters is not None and hasattr(self.variable_parameters, 'L'):
            pole_half_length = tf.convert_to_tensor(self.variable_parameters.L, dtype=tf.float32)
        else:
            pole_half_length = tf.convert_to_tensor(L, dtype=tf.float32)

        Q = Q[..., 0]  # Removes features dimension, specific for cartpole as it has only one control input
        u = Q2u_tf(Q)
        s_next = cartpole_fine_integration_tf(s, u=u, t_step=self.t_step, intermediate_steps=self.intermediate_steps, L=pole_half_length)

        return s_next


class predictor_output_augmentation_tf:
    def __init__(self, net_info, lib, disable_individual_compilation=False, differential_network=False):

        self.lib = lib

        self.differential_network = differential_network
        if differential_network:
            DIFF_NET_STATE_VARIABLES = [x[2:] for x in net_info.outputs]
            outputs = DIFF_NET_STATE_VARIABLES
        else:
            outputs = net_info.outputs

        self.net_output_indices = {key: value for value, key in enumerate(outputs)}
        indices_augmentation = []
        features_augmentation = []

        if 'angle' not in outputs and 'angle_sin' in outputs and 'angle_cos' in outputs:
            indices_augmentation.append(ANGLE_IDX)
            features_augmentation.append('angle')
        if 'angle_sin' not in outputs and 'angle' in outputs:
            indices_augmentation.append(ANGLE_SIN_IDX)
            features_augmentation.append('angle_sin')
        if 'angle_cos' not in outputs and 'angle' in outputs:
            indices_augmentation.append(ANGLE_COS_IDX)
            features_augmentation.append('angle_cos')

        self.indices_augmentation = indices_augmentation
        self.features_augmentation = features_augmentation
        self.augmentation_len = len(self.indices_augmentation)

        if 'angle' in outputs:
            self.index_angle = self.lib.to_tensor(self.net_output_indices['angle'], dtype=self.lib.int64)
        if 'angle_sin' in outputs:
            self.index_angle_sin = self.lib.to_tensor(self.net_output_indices['angle_sin'], dtype=self.lib.int64)
        if 'angle_cos' in outputs:
            self.index_angle_cos = self.lib.to_tensor(self.net_output_indices['angle_cos'], dtype=self.lib.int64)

        if disable_individual_compilation:
            self.augment = self._augment
        else:
            self.augment = CompileAdaptive(self._augment)

    def get_indices_augmentation(self):
        return self.indices_augmentation

    def get_features_augmentation(self):
        return self.features_augmentation

    def _augment(self, net_output):

        output = net_output  # [batch_size, time_steps, features]
        if 'angle' in self.features_augmentation:
            angle = self.lib.atan2(
                    net_output[..., self.index_angle_sin],
                    net_output[..., self.index_angle_cos])[:, :, self.lib.newaxis]  # self.lib.atan2 removes the features (last) dimension, so it is added back with [:, :, self.lib.newaxis]
            output = self.lib.concat([output, angle], axis=-1)

        if 'angle_sin' in self.features_augmentation:
            angle_sin = \
                self.lib.sin(net_output[..., self.index_angle])[:, :, self.lib.newaxis]
            output = self.lib.concat([output, angle_sin], axis=-1)

        if 'angle_cos' in self.features_augmentation:
            angle_cos = \
                self.lib.cos(net_output[..., self.index_angle])[:, :, self.lib.newaxis]
            output = self.lib.concat([output, angle_cos], axis=-1)

        return output
