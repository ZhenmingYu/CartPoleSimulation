from SI_Toolkit.load_and_normalize import add_shifted_columns

# # A = 'Test/Test-'
# # A = 'Validate/Validate-'
# A = 'Train/Train-'
# # B = '1s500ms'
# B = '27s'
# folder = A+B
# get_files_from = 'SI_Toolkit_ASF/Experiments/DG-27s-and-1s500ms-noisy/Recordings/'+folder
# save_files_to = 'SI_Toolkit_ASF/Experiments/DG-27s-and-1s500ms-noisy-u/Recordings/'+folder

get_files_from = './SI_Toolkit_ASF/Experiments/random_walk_new/10%_randomwalk_on_L_every_0.002s/Recordings/Train'
save_files_to = './SI_Toolkit_ASF/Experiments/random_walk_new/shifited_10%_randomwalk_on_L_every_0.002s/Recordings/Train'
get_files_from = './SI_Toolkit_ASF/Experiments/random_walk_new/10%_randomwalk_on_L_every_0.002s/Recordings/Validate/'
save_files_to = './SI_Toolkit_ASF/Experiments/random_walk_new/shifited_10%_randomwalk_on_L_every_0.002s/Recordings/Validate/'
get_files_from = './SI_Toolkit_ASF/Experiments/random_walk_new/10%_randomwalk_on_L_every_0.002s/Recordings/Test/'
save_files_to = './SI_Toolkit_ASF/Experiments/random_walk_new/shifited_10%_randomwalk_on_L_every_0.002s/Recordings/Test/'

variables_to_shift = ['angle', 'angleD', 'angleDD', 'angle_sin', 'angle_cos', 'position', 'positionD', 'positionDD', 'Q_applied']
indices_by_which_to_shift = [-1]

if __name__ == '__main__':
    add_shifted_columns(get_files_from, save_files_to, variables_to_shift, indices_by_which_to_shift)
