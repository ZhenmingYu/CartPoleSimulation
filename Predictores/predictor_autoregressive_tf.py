"""
This is a CLASS of predictor.
The idea is to decouple the estimation of system future state from the controller design.
While designing the controller you just chose the predictor you want,
 initialize it while initializing the controller and while stepping the controller you just give it current state
    and it returns the future states

"""

"""
This is a predictor for autoregressive RNNs constructed in tensorflowrol
This predictor is good only for one control input being first net input, all other net inputs in the same order
as net outputs, and all net outputs being closed loop, no dt, no target position
horizon cannot be changed in runtime
"""


"""
Using predictor:
1. Initialize while initializing controller
    This step load the RNN - it make take quite a bit of time
    During initialization you only need to provide RNN which should be loaded
2. Call iterativelly three functions
    a) setup(initial_state, horizon, etc.)
    b) predict(Q)
    c) update_net
    
    ad a) at this stage you can change the parameters for prediction like e.g. horizon, dt
            It also prepares 0 state of the prediction, and tensors for saving the results,
            to make b) max performance. This function should be called BEFORE starting solving an optim
    ad b) predict is optimized to get the prediction of future states of the system as fast as possible.
        It accepts control input (vector) as its only input and is intended to be used at every evaluation of the cost functiomn
    ad c) this method updates the internal state of RNN. It accepts control input for current time step (scalar) as its only input
            it should be called only after the optimization problem is solved with the control input used in simulation
            
"""

#TODO: for the moment it is not possible to update RNN more often than mpc dt
#   Updating it more often will lead to false results.

# "Command line" parameters
from Modeling.TF.Parameters import args
from Modeling.TF.TF_Functions.Network import *
from Modeling.TF.TF_Functions.Initialization import get_net_and_norm_info
from Modeling.load_and_normalize import *

from CartPole._CartPole_mathematical_helpers import *

import numpy as np
import pandas as pd


PREDICTION_FEATURES_NAMES = ['angle_cos', 'angle_sin', 'angleD', 'position', 'positionD']

net_name = 'GRU-6IN-64H1-64H2-5OUT-3'
PATH_TO_NORMALIZATION_INFO = './Modeling/NormalizationInfo/' + '250.csv'

# region Import and print "command line" arguments
print('')
a = args()  # 'a' like arguments
print(a.__dict__)
print('')
# endregion
a.net_name = net_name
a.path_to_normalization_info = PATH_TO_NORMALIZATION_INFO




class predictor_autoregressive_tf:
    def __init__(self, horizon, dt=None):

        self.horizon = horizon

        # Create a copy of the network suitable for inference (stateful and with sequence length one)
        self.net, self.net_info, self.normalization_info = \
            get_net_and_norm_info(a, time_series_length=1,
                                  batch_size=1, stateful=True)


        # Make a prediction

        self.Q_previous = None  # Motor power from last time step


        self.rnn_internal_states = get_internal_states(self.net)

        self.net_initial_input_without_Q = np.zeros([len(self.net_info.inputs) - 1], dtype=np.float32)
        # self.net_initial_input_without_Q_TF =

        self.prediction_denorm = None # Set to True or False in setup, determines if output should be denormalized

        self.states_history = np.zeros([self.horizon+1, len(STATE_VARIABLES)], dtype=np.float32)


        Q_type = tf.TensorSpec((self.horizon,), tf.float32)
        initial_input_type = tf.TensorSpec((len(self.net_info.inputs)-1,), tf.float32)

        net_input_type = tf.TensorSpec((1, 1, len(self.net_info.inputs)), tf.float32)



        # Retracing tensorflow functions
        try:
            self.evaluate_net = self.evaluate_net_f.get_concrete_function(net_input=net_input_type)
        except:
            self.evaluate_net = self.evaluate_net_f

        try:
            self.iterate_net = self.iterate_net_f.get_concrete_function(Q=Q_type,
                                                                        initial_input=initial_input_type)
            print(self.iterate_net)
        except:
            self.iterate_net = self.iterate_net_f

        print('Init done')

    def setup(self, initial_state: np.array, prediction_denorm=True):

        self.states_history[0, :] = initial_state

        initial_state_normed = normalize_numpy_array(initial_state, STATE_VARIABLES, self.normalization_info)

        # [1:] excludes Q which is not included in initial_state_normed
        # As the only feature written with big Q it should be first on each list.
        self.net_initial_input_without_Q = initial_state_normed[cartpole_state_varnames_to_indices(self.net_info.inputs[1:])]
        self.net_initial_input_without_Q_TF = tf.convert_to_tensor(self.net_initial_input_without_Q, tf.float32)

        if prediction_denorm:
            self.prediction_denorm=True
        else:
            self.prediction_denorm = False

        # print('Setup done')

    def predict(self, Q) -> np.array:
        # print('Prediction started')
        # load internal RNN state

        if len(Q) != self.horizon:
            raise IndexError('Number of provided control inputs does not match the horizon')
        else:
            Q = tf.squeeze(tf.convert_to_tensor(Q, dtype=tf.float32))

        load_internal_states(self.net, self.rnn_internal_states)
        # t0 = timeit.default_timer()
        net_outputs = self.iterate_net(Q)
        # t1 = timeit.default_timer()
        # iterate_t = (t1-t0)/self.horizon
        # print('Iterate {} us/eval'.format(iterate_t * 1.0e6))
        # compose the pandas output DF
        # Later: if necessary add sin, cos, derivatives
        # First version let us assume net returns all state except for angle
        net_outputs = net_outputs.numpy()

        # Denormalize
        self.states_history[1:, cartpole_state_varnames_to_indices(self.net_info.outputs)] = denormalize_numpy_array(net_outputs, self.net_info.outputs, self.normalization_info)

        # Augment
        if 'angle' not in self.net_info.outputs:
            self.states_history[:, cartpole_state_varname_to_index('angle')] = \
                np.arctan2(
                    self.states_history[:, cartpole_state_varname_to_index('angle_sin')],
                    self.states_history[:, cartpole_state_varname_to_index('angle_cos')])
        if 'angle_sin' not in self.net_info.outputs:
            self.states_history[:, cartpole_state_varname_to_index('angle_sin')] =\
                np.sin(self.states_history[:, cartpole_state_varname_to_index('angle')])
        if 'angle_cos' not in self.net_info.outputs:
            self.states_history[:, cartpole_state_varname_to_index('angle_cos')] =\
                np.sin(self.states_history[:, cartpole_state_varname_to_index('angle')])

        return self.states_history

    # @tf.function
    def update_internal_state(self, Q0):
        # load internal RNN state
        load_internal_states(self.net, self.rnn_internal_states)

        # Run current input through network
        Q0 = tf.squeeze(tf.convert_to_tensor(Q0, dtype=tf.float32))
        Q0 = (tf.reshape(Q0, [1]))
        if self.net_info.net_type == 'Dense':
            net_input = (tf.reshape(tf.concat([Q0, self.net_initial_input_without_Q_TF], axis=0),
                                    [1, len(self.net_info.inputs)]))
        else:
            net_input = (tf.reshape(tf.concat([Q0, self.net_initial_input_without_Q_TF], axis=0),
                                    [1, 1, len(self.net_info.inputs)]))
        # self.evaluate_net(self.net_current_input) # Using tf.function to compile net
        self.net(net_input)  # Using net directly

        get_internal_states(self.net)

    @tf.function
    def iterate_net_f(self, Q):
        print('retracing iterate_net_f')
        # Iterate over RNN -
        # net_input = tf.zeros(shape=(1, 1, len(self.net_info.inputs),), dtype=tf.float32)
        # net_output = tf.zeros(shape=(1,len(self.net_outputs_names)), dtype=tf.float32)
        net_outputs = tf.TensorArray(tf.float32, size=self.horizon)
        net_output = tf.zeros(shape=(len(self.net_info.outputs)), dtype=tf.float32)
        # Q_current = tf.zeros(shape=(1,), dtype=tf.float32)

        # net_inout = net_inout.write(0, tf.reshape(initial_input, [1, len(initial_input)]))
        for i in tf.range(0, self.horizon):
            Q_current = (tf.reshape(Q[i], [1]))
            if i == 0:
                if self.net_info.net_type == 'Dense':
                    net_input = (tf.reshape(tf.concat([Q_current, self.net_initial_input_without_Q_TF], axis=0), [1, len(self.net_info.inputs)]))
                else:
                    net_input = (tf.reshape(tf.concat([Q_current, self.net_initial_input_without_Q_TF], axis=0), [1, 1, len(self.net_info.inputs)]))
            else:
                if self.net_info.net_type == 'Dense':
                    net_input = tf.reshape(tf.concat([Q_current, net_output], axis=0), [1, len(self.net_info.inputs)])
                else:
                    net_input = tf.reshape(tf.concat([Q_current, net_output], axis=0), [1, 1, len(self.net_info.inputs)])
            # net_output = self.net(net_input)
            net_output = tf.squeeze(self.evaluate_net(net_input))
            #tf.print(net_output)

            net_outputs = net_outputs.write(i, net_output)
            # tf.print(net_inout.read(i+1))
        # print(net_inout)
        net_outputs = net_outputs.stack()
        return net_outputs

    @tf.function
    def evaluate_net_f(self, net_input):
        print('retracing evaluate_net_f')
        net_output = self.net(net_input)
        return net_output