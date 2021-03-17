# -*- coding: utf-8 -*-
"""
Testing network predictions for CartPole
"""

# "Command line" parameters
from Modeling.TF.Parameters import args

# Custom functions
from Modeling.TF.TF_Functions.Test_predictions import get_data_for_gui_TF
from get_prediction_from_euler import get_prediction_from_euler

from Modeling.Testing.Brunton_GUI import run_test_gui


from copy import deepcopy

# region Import and print "command line" arguments
print('')
a = args()  # 'a' like arguments
print(a.__dict__)
print('')
# endregion


def test_network():

    """
    This function create RNN instance based on parameters saved on disc and also creates the CartPole instance.
    The actual work of evaluation prediction results is done in get_predictions_TF function
    """

    # Get first dataset

    inputs, outputs, title_1,\
    ground_truth, net_outputs, time_axis\
        = get_data_for_gui_TF(a)

    # # Get second dataset
    # a_new = deepcopy(a)
    # a_new.net_name = 'GRU-6IN-64H1-64H2-5OUT-0'
    # _, _, title_2,\
    # _, dataset_2, _\
    #     = get_data_for_gui_TF(a_new)


    inputs_euler, outputs_euler, title_2, \
    _, dataset_euler, _ \
        = get_prediction_from_euler(a)

    # Get second dataset from Euler
    output_indexes = []
    for element in outputs:
        output_indexes.append(outputs_euler.index(element))
    dataset_2 = dataset_euler[:, :, output_indexes]

    run_test_gui(inputs, outputs,
                 ground_truth, net_outputs, time_axis,
                 net_outputs_2=dataset_2,
                 datasets_titles=[title_1, title_2]
                 )

if __name__ == '__main__':
    test_network()
