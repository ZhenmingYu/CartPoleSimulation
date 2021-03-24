"""
Model Predictive Path Integral Controller
Based on Williams, Aldrich, Theodorou (2015)
"""
from Controllers.template_controller import template_controller
from CartPole.cartpole_model import (
    P_GLOBALS,
    Q2u,
    _cartpole_ode,
    k,
    M,
    m,
    g,
    J_fric,
    M_fric,
    L,
    v_max,
    u_max,
    TrackHalfLength,
)
from CartPole._CartPole_mathematical_helpers import (
    create_cartpole_state,
    cartpole_state_varname_to_index,
    conditional_decorator,
)

import matplotlib.pyplot as plt
import numpy as np
from numba import jit

from copy import deepcopy


"""Timestep and sampling settings"""
dt = 0.02  # s
mpc_horizon = 1.0
mpc_samples = int(mpc_horizon / dt)  # Number of steps in MPC horizon
mc_samples = 4000  # Number of Monte Carlo samples


"""Define indices of values in state statically"""
ANGLE_IDX = cartpole_state_varname_to_index("angle").item()
ANGLED_IDX = cartpole_state_varname_to_index("angleD").item()
POSITION_IDX = cartpole_state_varname_to_index("position").item()
POSITIOND_IDX = cartpole_state_varname_to_index("positionD").item()


"""MPPI constants"""
R = 1.0e0  # How much to punish Q
LBD = 10  # Cost parameter lambda
NU = 1.0e1  # Exploration variance


"""Set up parallelization"""
parallelize = True
_cartpole_ode = conditional_decorator(jit(nopython=True), parallelize)(_cartpole_ode)


"""Init logging variables"""
DEBUG = False
# Save average cost for each cost component
COST_LOGS = []


"""Cost function helpers"""
E_kin_cart = conditional_decorator(jit(nopython=True), parallelize)(
    lambda s: (s[POSITIOND_IDX] / v_max) ** 2
)
E_kin_pol = conditional_decorator(jit(nopython=True), parallelize)(
    lambda s: (s[ANGLED_IDX] / (2 * np.pi)) ** 2
)
E_pot_cost = conditional_decorator(jit(nopython=True), parallelize)(
    lambda s: (1 - np.cos(s[ANGLE_IDX])) ** 2
)
distance_difference = conditional_decorator(jit(nopython=True), parallelize)(
    lambda s, target_position: ((s[POSITION_IDX] - target_position) / TrackHalfLength)
    ** 2
)


@conditional_decorator(jit(nopython=True), parallelize)
def cartpole_ode_parallelize(s: np.ndarray, u: float):
    """Wrapper for the _cartpole_ode function"""
    return _cartpole_ode(
        s[ANGLE_IDX], s[ANGLED_IDX], s[POSITION_IDX], s[POSITIOND_IDX], u
    )


@conditional_decorator(jit(nopython=True), parallelize)
def trajectory_rollouts(s, S_tilde_k, u, delta_u, target_position):
    s_horizon = np.zeros((mc_samples, mpc_samples, s.size))
    for k in range(mc_samples):
        s_horizon[k, 0, :] = s
        for i in range(1, mpc_samples):
            s_last = s_horizon[k, i - 1, :]
            # Explicit Euler integration step
            derivatives = motion_derivatives(s_last, u[i] + delta_u[k, i])
            s_next = s_last + derivatives * dt
            s_horizon[k, i, :] = s_next

            cost_increment, _, _, _, _, _ = q(
                s_next, u[i], delta_u[k, i], target_position
            )
            S_tilde_k[k] += cost_increment

    return S_tilde_k, None


@conditional_decorator(jit(nopython=True), parallelize)
def trajectory_rollouts_debug(s, S_tilde_k, u, delta_u, target_position):
    s_horizon = np.zeros((mc_samples, mpc_samples, s.size))
    cost_logs_internal = np.zeros((mc_samples, 5, mpc_samples))
    for k in range(mc_samples):
        s_horizon[k, 0, :] = s
        for i in range(1, mpc_samples):
            s_last = s_horizon[k, i - 1, :]
            # Explicit Euler integration step
            derivatives = motion_derivatives(s_last, u[i] + delta_u[k, i])
            s_next = s_last + derivatives * dt
            s_horizon[k, i, :] = s_next

            cost_increment, dd, ep, ekp, ekc, cc = q(
                s_next, u[i], delta_u[k, i], target_position
            )
            S_tilde_k[k] += cost_increment
            cost_logs_internal[k, :, i] = [dd, ep, ekp, ekc, cc]

    return S_tilde_k, cost_logs_internal


rollout_function = trajectory_rollouts_debug if DEBUG else trajectory_rollouts


@conditional_decorator(jit(nopython=True), parallelize)
def motion_derivatives(s: np.ndarray, u: float):
    """
    :return: The vector of angle, angleD, position, positionD time derivatives
    """
    s_dot = np.zeros_like(s)
    s_dot[POSITION_IDX] = s[POSITIOND_IDX]
    s_dot[ANGLE_IDX] = s[ANGLED_IDX]
    (s_dot[ANGLED_IDX], s_dot[POSITIOND_IDX]) = cartpole_ode_parallelize(s, u_max * u)
    return s_dot


@conditional_decorator(jit(nopython=True), parallelize)
def q(s, u, delta_u, target_position):
    """Cost function per iteration"""
    dd = distance_difference(s, target_position) * 1.0e4
    ep = 100 * E_pot_cost(s)
    ekp = E_kin_pol(s)
    ekc = 100 * E_kin_cart(s)
    cc = (
        0.5 * (1 - 1.0 / NU) * R * (delta_u ** 2) + R * u * delta_u + 0.5 * R * (u ** 2)
    )

    q = dd + ep + ekp + ekc + cc

    if np.abs(u + delta_u) > 1.0:
        q = 1.0e5

    return q, dd, ep, ekp, ekc, cc


@conditional_decorator(jit(nopython=True), parallelize)
def reward_weighted_average(S_i, delta_u_i):
    """Average the perturbations delta_u based on their desirability"""
    rho = np.min(S_i)  # for numerical stability
    exp_s = np.exp(-1.0 / LBD * (S_i - rho))
    a = np.sum(exp_s)
    b = np.sum(np.multiply(exp_s, delta_u_i) / a)
    return b


@conditional_decorator(jit(nopython=True), parallelize)
def update_inputs(u: np.ndarray, S: np.ndarray, delta_u: np.ndarray):
    """
    :param u: Sampling mean / warm started control inputs of size (,mpc_samples)
    :param S: Cost array of size (mc_samples)
    :param delta_u: The input perturbations that had been used, size (mc_samples, mpc_samples)

    :return: Input u for the whole MPC horizon updated with reward-weighted control perturbations
    """
    for i in range(mpc_samples):
        u[i] += reward_weighted_average(S, delta_u[:, i])
    return u


class controller_mppi(template_controller):
    def __init__(self):
        # State of the cart
        self.s = create_cartpole_state()

        np.random.seed(123)

        self.target_position = 0.0

        self.rho_sqrt_inv = 0.01
        self.avg_cost = []

        self.iteration = 0

        self.s_horizon = np.zeros(())
        self.u = np.zeros((mpc_samples), dtype=float)
        self.delta_u = np.zeros((mc_samples, mpc_samples), dtype=float)
        self.S_tilde_k = np.zeros((mc_samples), dtype=float)

    def initialize_perturbations(
        self, stdev: float = 1.0, random_walk: bool = False, uniform: bool = False
    ) -> np.ndarray:
        """
        Return a numpy array with the perturbations delta_u.
        If random_walk is false, initialize with independent Gaussian samples
        If random_walk is true, each row represents a 1D random walk with Gaussian steps.
        """
        if random_walk:
            delta_u = np.zeros((mc_samples, mpc_samples), dtype=float)
            delta_u[:, 0] = stdev * np.random.normal(size=(mc_samples,))
            for i in range(1, mpc_samples):
                delta_u[:, i] = delta_u[:, i - 1] + stdev * np.random.normal(
                    size=(mc_samples,)
                )
        elif uniform:
            delta_u = np.zeros((mc_samples, mpc_samples), dtype=float)
            for i in range(0, mpc_samples):
                delta_u[:, i] = (
                    np.random.uniform(low=-1.0, high=1.0, size=(mc_samples,))
                    - self.u[i]
                )
        else:
            delta_u = stdev * np.random.normal(size=np.shape(self.delta_u))

        return delta_u

    def step(self, s, target_position, time=None):
        self.s = s
        self.target_position = target_position.item()

        self.iteration += 1

        # Initialize perturbations and cost arrays
        # self.delta_u = self.initialize_perturbations(
        #     stdev=self.rho_sqrt_inv / np.sqrt(dt), random_walk=False
        # )  # N(mean=0, var=1/(rho*dt))
        self.delta_u = self.initialize_perturbations(stdev=0.2)
        self.S_tilde_k = np.zeros_like(self.S_tilde_k)

        # Run parallel trajectory rollouts for different input perturbations
        self.S_tilde_k, cost_logs_internal = rollout_function(
            self.s, self.S_tilde_k, self.u, self.delta_u, self.target_position,
        )

        if DEBUG:
            self.avg_cost.append(np.mean(self.S_tilde_k, axis=0))
            COST_LOGS.append(np.mean(cost_logs_internal, axis=0))

        # Update inputs with weighted perturbations
        self.u = update_inputs(self.u, self.S_tilde_k, self.delta_u)

        Q = np.clip(self.u[0], -1, 1)
        # Q = self.u[0]

        # Index shift inputs
        self.u[:-1] = self.u[1:]
        # self.u[-1] = 0

        return Q  # normed control input in the range [-1,1]

    def controller_report(self):
        if DEBUG:
            # Graph the average state cost per iteration
            time_axis = dt * np.arange(start=0, stop=len(self.avg_cost))
            plt.figure(num=2, figsize=(8, 8))
            plt.plot(time_axis, self.avg_cost)
            plt.ylabel("avg_cost")
            plt.xlabel("time")
            plt.title("Cost over iterations")
            plt.show()

            clgs = np.stack(COST_LOGS, axis=0)  # ITERATIONS x 5 x mpc_steps
            plt.figure(num=3, figsize=(12, 8))
            plt.plot(
                clgs[:, 0, 1], label="Distance difference cost",
            )
            plt.plot(clgs[:, 1, 1], label="E_pot cost")
            plt.plot(clgs[:, 2, 1], label="E_kin_pole cost")
            plt.plot(clgs[:, 3, 1], label="E_kin_cart cost")
            plt.plot(clgs[:, 4, 1], label="Control cost")
            plt.title("Cost of each first MPC horizon step over time")
            plt.legend()
            plt.show()

    # Optionally: reset the controller after an experiment
    # May be useful for stateful controllers, like these containing RNN,
    # To reload the hidden states e.g. if the controller went unstable in the previous run.
    # It is called after an experiment,
    # but only if the controller is supposed to be reused without reloading (e.g. in GUI)
    def controller_reset(self):
        pass
