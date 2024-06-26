"""
MIT License

Copyright (c) 2020-present TorchQuantum Authors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

import functools
import torch
import numpy as np

from typing import Callable, Union, Optional, List, Dict, TYPE_CHECKING
from ..macro import C_DTYPE, F_DTYPE, ABC, ABC_ARRAY, INV_SQRT2
from ..util.utils import pauli_eigs, diag
#from torchpack.utils.logging import logger
from torchquantum.util import normalize_statevector

if TYPE_CHECKING:
    from torchquantum.device import QuantumDevice
else:
    QuantumDevice = None

__all__ = [
    "func_name_dict",
    "mat_dict",
    "apply_unitary_einsum",
    "apply_unitary_bmm",
    "hadamard",
    "shadamard",
    "paulix",
    "pauliy",
    "pauliz",
    "i",
    "s",
    "t",
    "sx",
    "cnot",
    "cz",
    "cy",
    "swap",
    "sswap",
    "cswap",
    "toffoli",
    "multicnot",
    "multixcnot",
    "rx",
    "ry",
    "rz",
    "rxx",
    "ryy",
    "rzz",
    "rzx",
    "phaseshift",
    "rot",
    "multirz",
    "crx",
    "cry",
    "crz",
    "crot",
    "u1",
    "u2",
    "u3",
    "cu",
    "cu1",
    "cu2",
    "cu3",
    "kron",
    "su4",
    "qubitunitary",
    "qubitunitaryfast",
    "qubitunitarystrict",
    "singleexcitation",
    "h",
    "sh",
    "x",
    "y",
    "z",
    "xx",
    "yy",
    "zz",
    "zx",
    "cx",
    "ccnot",
    "ccx",
    "u",
    "cu",
    "p",
    "cp",
    "cr",
    "cphase",
    "reset",
    "ecr",
    "echoedcrossresonance",
    "qft",
    "sdg",
    "iswap",
    "cs",
    "csdg",
    "csx",
    "chadamard",
    "ccz",
    "dcx",
    "xxminyy",
    "xxplusyy",
    "c3x",
    "tdg",
    "sxdg",
    "ch",
    "r",
    "c4x",
    "rccx",
    "rc3x",
    "globalphase",
    "c3sx",
]


def apply_unitary_einsum(state, mat, wires):
    """Apply the unitary to the statevector using torch.einsum method.

    Args:
        state (torch.Tensor): The statevector.
        mat (torch.Tensor): The unitary matrix of the operation.
        wires (int or List[int]): Which qubit the operation is applied to.

    Returns:
        torch.Tensor: The new statevector.

    """
    device_wires = wires

    # minus one because of batch
    total_wires = len(state.shape) - 1

    if len(mat.shape) > 2:
        is_batch_unitary = True
        bsz = mat.shape[0]
        shape_extension = [bsz]
        # try:
        #     assert state.shape[0] == bsz
        # except AssertionError as err:
        #     logger.exception(f"Batch size of Quantum Device must be the same"
        #                      f" with that of gate unitary matrix")
        #     raise err

    else:
        is_batch_unitary = False
        shape_extension = []

    mat = mat.view(shape_extension + [2] * len(device_wires) * 2)

    mat = mat.type(C_DTYPE).to(state.device)

    # Tensor indices of the quantum state
    state_indices = ABC[:total_wires]

    # Indices of the quantum state affected by this operation
    affected_indices = "".join(ABC_ARRAY[list(device_wires)].tolist())

    # All affected indices will be summed over, so we need the same number
    # of new indices
    new_indices = ABC[total_wires : total_wires + len(device_wires)]

    # The new indices of the state are given by the old ones with the
    # affected indices replaced by the new_indices
    new_state_indices = functools.reduce(
        lambda old_string, idx_pair: old_string.replace(idx_pair[0], idx_pair[1]),
        zip(affected_indices, new_indices),
        state_indices,
    )

    # try:
    #     cannot support too many qubits...
    #     assert ABC[-1] not in state_indices + new_state_indices  \
    #      + new_indices + affected_indices
    # except AssertionError as err:
    #     logger.exception(f"Cannot support too many qubit.")
    #     raise err

    state_indices = ABC[-1] + state_indices
    new_state_indices = ABC[-1] + new_state_indices
    if is_batch_unitary:
        new_indices = ABC[-1] + new_indices

    # We now put together the indices in the notation numpy einsum
    # requires
    einsum_indices = (
        f"{new_indices}{affected_indices}," f"{state_indices}->{new_state_indices}"
    )

    new_state = torch.einsum(einsum_indices, mat, state)

    return new_state


def apply_unitary_bmm(state, mat, wires):
    """Apply the unitary to the statevector using torch.bmm method.

    Args:
        state (torch.Tensor): The statevector.
        mat (torch.Tensor): The unitary matrix of the operation.
        wires (int or List[int]): Which qubit the operation is applied to.

    Returns:
        torch.Tensor: The new statevector.

    """
    device_wires = wires

    # if len(mat.shape) > 2:
    #         bsz = mat.shape[0]
    #     try:
    #         assert state.shape[0] == bsz
    #     except AssertionError as err:
    #         logger.exception(f"Batch size of Quantum Device must be the same"
    #                          f" with that of gate unitary matrix")
    #         raise err
    mat = mat.type(C_DTYPE).to(state.device)

    devices_dims = [w + 1 for w in device_wires]
    permute_to = list(range(state.dim()))
    for d in sorted(devices_dims, reverse=True):
        del permute_to[d]
    permute_to = permute_to[:1] + devices_dims + permute_to[1:]
    permute_back = list(np.argsort(permute_to))
    original_shape = state.shape
    permuted = state.permute(permute_to).reshape([original_shape[0], mat.shape[-1], -1])

    if len(mat.shape) > 2:
        # both matrix and state are in batch mode
        new_state = mat.bmm(permuted)
    else:
        # matrix no batch, state in batch mode
        bsz = permuted.shape[0]
        expand_shape = [bsz] + list(mat.shape)
        new_state = mat.expand(expand_shape).bmm(permuted)

    new_state = new_state.view(original_shape).permute(permute_back)

    return new_state


def gate_wrapper(
    name,
    mat,
    method,
    q_device: QuantumDevice,
    wires,
    params=None,
    n_wires=None,
    static=False,
    parent_graph=None,
    inverse=False,
):
    """Perform the phaseshift gate.

    Args:
        name (str): The name of the operation.
        mat (torch.Tensor): The unitary matrix of the gate.
        method (str): 'bmm' or 'einsum' to compute matrix vector
            multiplication.
        q_device (tq.QuantumDevice): The QuantumDevice.
        wires (Union[List[int], int]): Which qubit(s) to apply the gate.
        params (torch.Tensor, optional): Parameters (if any) of the gate.
            Default to None.
        n_wires (int, optional): Number of qubits the gate is applied to.
            Default to None.
        static (bool, optional): Whether use static mode computation.
            Default to False.
        parent_graph (tq.QuantumGraph, optional): Parent QuantumGraph of
            current operation. Default to None.
        inverse (bool, optional): Whether inverse the gate. Default to False.
        comp_method (bool, optional): Use 'bmm' or 'einsum' method to perform
        matrix vector multiplication. Default to 'bmm'.

    Returns:
        None.

    """
    if params is not None:
        if not isinstance(params, torch.Tensor):
            if name in ["qubitunitary", "qubitunitaryfast", "qubitunitarystrict"]:
                # this is for qubitunitary gate
                params = torch.tensor(params, dtype=C_DTYPE)
            else:
                # this is for directly inputting parameters as a number
                params = torch.tensor(params, dtype=F_DTYPE)

        if name in ["qubitunitary", "qubitunitaryfast", "qubitunitarystrict"]:
            params = params.unsqueeze(0) if params.dim() == 2 else params
        else:
            if params.dim() == 1:
                params = params.unsqueeze(-1)
            elif params.dim() == 0:
                params = params.unsqueeze(-1).unsqueeze(-1)
            # params = params.unsqueeze(-1) if params.dim() == 1 else params
    wires = [wires] if isinstance(wires, int) else wires

    if q_device.record_op:
        q_device.op_history.append(
            {
                "name": name,  # type: ignore
                "wires": np.array(wires).squeeze().tolist(),
                "params": params.squeeze().detach().cpu().numpy().tolist()
                if params is not None
                else None,
                "inverse": inverse,
                "trainable": params.requires_grad if params is not None else False,
            }
        )

    if static:
        # in static mode, the function is not computed immediately, instead,
        # the unitary of a module will be computed and then applied
        parent_graph.add_func(
            name=name,
            wires=wires,
            parent_graph=parent_graph,
            params=params,
            n_wires=n_wires,
            inverse=inverse,
        )
    else:
        # in dynamic mode, the function is computed instantly
        if isinstance(mat, Callable):
            if n_wires is None or name in [
                "qubitunitary",
                "qubitunitaryfast",
                "qubitunitarystrict",
            ]:
                matrix = mat(params)
            elif name in ["multicnot", "multixcnot", "qft"]:
                # this is for gates that can be applied to arbitrary numbers of
                # qubits but no params, such as multicnot
                matrix = mat(n_wires)
            elif name in ["multirz"]:
                # this is for gates that can be applied to arbitrary numbers of
                # qubits such as multirz
                matrix = mat(params, n_wires)
            else:
                matrix = mat(params)

        else:
            matrix = mat

        if inverse:
            matrix = matrix.conj()
            if matrix.dim() == 3:
                matrix = matrix.permute(0, 2, 1)
            else:
                matrix = matrix.permute(1, 0)
        assert np.log2(matrix.shape[-1]) == len(wires)
        state = q_device.states
        if method == "einsum":
            q_device.states = apply_unitary_einsum(state, matrix, wires)
        elif method == "bmm":
            q_device.states = apply_unitary_bmm(state, matrix, wires)


def reset(q_device: QuantumDevice, wires, inverse=False):
    # reset the target qubits to 0, non-unitary operation
    state = q_device.states

    wires = [wires] if isinstance(wires, int) else wires

    for wire in wires:
        devices_dim = wire + 1
        permute_to = list(range(state.dim()))
        del permute_to[devices_dim]
        permute_to += [devices_dim]
        permute_back = list(np.argsort(permute_to))

        # permute the target wire to the last dim
        permuted = state.permute(permute_to)

        # reset the state
        permuted[..., 1] = 0

        # permute back
        state = state.permute(permute_back)

    # normalize the magnitude of states
    q_device.states = normalize_statevector(q_device.states)


def rx_matrix(params: torch.Tensor) -> torch.Tensor:
    """Compute unitary matrix for rx gate.

    Args:
        params (torch.Tensor): The rotation angle.

    Returns:
        torch.Tensor: The computed unitary matrix.

    """
    theta = params.type(C_DTYPE)
    """
    Seems to be a pytorch bug. Have to explicitly cast the theta to a
    complex number. If directly theta = params, then get error:

    allow_unreachable=True, accumulate_grad=True)  # allow_unreachable flag
    RuntimeError: Expected isFloatingType(grad.scalar_type()) ||
    (input_is_complex == grad_is_complex) to be true, but got false.
    (Could this error message be improved?
    If so, please report an enhancement request to PyTorch.)

    """
    co = torch.cos(theta / 2)
    jsi = 1j * torch.sin(-theta / 2)

    return torch.stack(
        [torch.cat([co, jsi], dim=-1), torch.cat([jsi, co], dim=-1)], dim=-2
    ).squeeze(0)


def ry_matrix(params: torch.Tensor) -> torch.Tensor:
    """Compute unitary matrix for ry gate.

    Args:
        params: The rotation angle.

    Returns:
        The computed unitary matrix.

    """
    theta = params.type(C_DTYPE)

    co = torch.cos(theta / 2)
    si = torch.sin(theta / 2)

    return torch.stack(
        [torch.cat([co, -si], dim=-1), torch.cat([si, co], dim=-1)], dim=-2
    ).squeeze(0)


def rz_matrix(params: torch.Tensor) -> torch.Tensor:
    """Compute unitary matrix for rz gate.

    Args:
        params: The rotation angle.

    Returns:
        The computed unitary matrix.

    """
    theta = params.type(C_DTYPE)
    exp = torch.exp(-0.5j * theta)

    return torch.stack(
        [
            torch.cat([exp, torch.zeros(exp.shape, device=params.device)], dim=-1),
            torch.cat(
                [torch.zeros(exp.shape, device=params.device), torch.conj(exp)], dim=-1
            ),
        ],
        dim=-2,
    ).squeeze(0)


def phaseshift_matrix(params):
    """Compute unitary matrix for phaseshift gate.

    Args:
        params (torch.Tensor): The rotation angle.

    Returns:
        torch.Tensor: The computed unitary matrix.

    """
    phi = params.type(C_DTYPE)
    exp = torch.exp(1j * phi)

    return torch.stack(
        [
            torch.cat(
                [
                    torch.ones(exp.shape, device=params.device),
                    torch.zeros(exp.shape, device=params.device),
                ],
                dim=-1,
            ),
            torch.cat([torch.zeros(exp.shape, device=params.device), exp], dim=-1),
        ],
        dim=-2,
    ).squeeze(0)


def rot_matrix(params):
    """Compute unitary matrix for rot gate.

    Args:
        params (torch.Tensor): The rotation angle.

    Returns:
        torch.Tensor: The computed unitary matrix.

    """
    phi = params[:, 0].unsqueeze(dim=-1).type(C_DTYPE)
    theta = params[:, 1].unsqueeze(dim=-1).type(C_DTYPE)
    omega = params[:, 2].unsqueeze(dim=-1).type(C_DTYPE)

    co = torch.cos(theta / 2)
    si = torch.sin(theta / 2)

    return torch.stack(
        [
            torch.cat(
                [
                    torch.exp(-0.5j * (phi + omega)) * co,
                    -torch.exp(0.5j * (phi - omega)) * si,
                ],
                dim=-1,
            ),
            torch.cat(
                [
                    torch.exp(-0.5j * (phi - omega)) * si,
                    torch.exp(0.5j * (phi + omega)) * co,
                ],
                dim=-1,
            ),
        ],
        dim=-2,
    ).squeeze(0)


def xxminyy_matrix(params):
    """Compute unitary matrix for XXminusYY gate.

    Args:
        params (torch.Tensor): The rotation angle. (Theta,Beta)

    Returns:
        torch.Tensor: The computed unitary matrix.

    """
    theta = params[:, 0].unsqueeze(dim=-1).type(C_DTYPE)
    beta = params[:, 1].unsqueeze(dim=-1).type(C_DTYPE)

    co = torch.cos(theta / 2)
    si = torch.sin(theta / 2)

    return torch.stack(
        [
            torch.cat(
                [
                    co,
                    torch.tensor([[0]]),
                    torch.tensor([[0]]),
                    (-1j * si * torch.exp(-1j * beta)),
                ],
                dim=-1,
            ),
            torch.cat(
                [
                    torch.tensor([[0]]),
                    torch.tensor([[1]]),
                    torch.tensor([[0]]),
                    torch.tensor([[0]]),
                ],
                dim=-1,
            ),
            torch.cat(
                [
                    torch.tensor([[0]]),
                    torch.tensor([[0]]),
                    torch.tensor([[1]]),
                    torch.tensor([[0]]),
                ],
                dim=-1,
            ),
            torch.cat(
                [
                    (-1j * si * torch.exp(1j * beta)),
                    torch.tensor([[0]]),
                    torch.tensor([[0]]),
                    co,
                ],
                dim=-1,
            ),
        ],
        dim=-2,
    ).squeeze(0)


def xxplusyy_matrix(params):
    """Compute unitary matrix for XXplusYY gate.

    Args:
        params (torch.Tensor): The rotation angle. (Theta,Beta)

    Returns:
        torch.Tensor: The computed unitary matrix.

    """
    theta = params[:, 0].unsqueeze(dim=-1).type(C_DTYPE)
    beta = params[:, 1].unsqueeze(dim=-1).type(C_DTYPE)

    co = torch.cos(theta / 2)
    si = torch.sin(theta / 2)

    return torch.stack(
        [
            torch.cat(
                [
                    torch.tensor([[1]]),
                    torch.tensor([[0]]),
                    torch.tensor([[0]]),
                    torch.tensor([[0]]),
                ],
                dim=-1,
            ),
            torch.cat(
                [
                    torch.tensor([[0]]),
                    co,
                    (-1j * si * torch.exp(1j * beta)),
                    torch.tensor([[0]]),
                ],
                dim=-1,
            ),
            torch.cat(
                [
                    torch.tensor([[0]]),
                    (-1j * si * torch.exp(-1j * beta)),
                    co,
                    torch.tensor([[0]]),
                ],
                dim=-1,
            ),
            torch.cat(
                [
                    torch.tensor([[0]]),
                    torch.tensor([[0]]),
                    torch.tensor([[0]]),
                    torch.tensor([[1]]),
                ],
                dim=-1,
            ),
        ],
        dim=-2,
    ).squeeze(0)


def multirz_eigvals(params, n_wires):
    """Compute eigenvalue for multiqubit RZ gate.

    Args:
        params (torch.Tensor): The rotation angle.

    Returns:
        torch.Tensor: The computed eigenvalues.

    """
    theta = params.type(C_DTYPE)
    return torch.exp(
        -1j * theta / 2 * torch.tensor(pauli_eigs(n_wires)).to(params.device)
    )


def multirz_matrix(params, n_wires):
    """Compute unitary matrix for multiqubit RZ gate.

    Args:
        params (torch.Tensor): The rotation angle.

    Returns:
        torch.Tensor: The computed unitary matrix.

    """
    # torch diagonal not available for complex number
    eigvals = multirz_eigvals(params, n_wires)
    dia = diag(eigvals)
    return dia.squeeze(0)


def rxx_matrix(params):
    """Compute unitary matrix for RXX gate.

    Args:
        params (torch.Tensor): The rotation angle.

    Returns:
        torch.Tensor: The computed unitary matrix.

    """

    theta = params.type(C_DTYPE)
    co = torch.cos(theta / 2)
    jsi = 1j * torch.sin(theta / 2)

    matrix = (
        torch.tensor(
            [[0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]],
            dtype=C_DTYPE,
            device=params.device,
        )
        .unsqueeze(0)
        .repeat(co.shape[0], 1, 1)
    )

    matrix[:, 0, 0] = co[:, 0]
    matrix[:, 1, 1] = co[:, 0]
    matrix[:, 2, 2] = co[:, 0]
    matrix[:, 3, 3] = co[:, 0]

    matrix[:, 0, 3] = -jsi[:, 0]
    matrix[:, 1, 2] = -jsi[:, 0]
    matrix[:, 2, 1] = -jsi[:, 0]
    matrix[:, 3, 0] = -jsi[:, 0]

    return matrix.squeeze(0)


def ryy_matrix(params):
    """Compute unitary matrix for RYY gate.

    Args:
        params (torch.Tensor): The rotation angle.

    Returns:
        torch.Tensor: The computed unitary matrix.

    """
    theta = params.type(C_DTYPE)
    co = torch.cos(theta / 2)
    jsi = 1j * torch.sin(theta / 2)

    matrix = (
        torch.tensor(
            [[0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]],
            dtype=C_DTYPE,
            device=params.device,
        )
        .unsqueeze(0)
        .repeat(co.shape[0], 1, 1)
    )

    matrix[:, 0, 0] = co[:, 0]
    matrix[:, 1, 1] = co[:, 0]
    matrix[:, 2, 2] = co[:, 0]
    matrix[:, 3, 3] = co[:, 0]

    matrix[:, 0, 3] = jsi[:, 0]
    matrix[:, 1, 2] = -jsi[:, 0]
    matrix[:, 2, 1] = -jsi[:, 0]
    matrix[:, 3, 0] = jsi[:, 0]

    return matrix.squeeze(0)


def rzz_matrix(params):
    """Compute unitary matrix for RZZ gate.

    Args:
        params (torch.Tensor): The rotation angle.

    Returns:
        torch.Tensor: The computed unitary matrix.

    """
    theta = params.type(C_DTYPE)
    exp = torch.exp(-0.5j * theta)
    conj_exp = torch.conj(exp)

    matrix = (
        torch.tensor(
            [[0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]],
            dtype=C_DTYPE,
            device=params.device,
        )
        .unsqueeze(0)
        .repeat(exp.shape[0], 1, 1)
    )

    matrix[:, 0, 0] = exp[:, 0]
    matrix[:, 1, 1] = conj_exp[:, 0]
    matrix[:, 2, 2] = conj_exp[:, 0]
    matrix[:, 3, 3] = exp[:, 0]

    return matrix.squeeze(0)


def rzx_matrix(params):
    """Compute unitary matrix for RZX gate.

    Args:
        params (torch.Tensor): The rotation angle.

    Returns:
        torch.Tensor: The computed unitary matrix.

    """
    theta = params.type(C_DTYPE)
    co = torch.cos(theta / 2)
    jsi = 1j * torch.sin(theta / 2)

    matrix = (
        torch.tensor(
            [[0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]],
            dtype=C_DTYPE,
            device=params.device,
        )
        .unsqueeze(0)
        .repeat(co.shape[0], 1, 1)
    )

    matrix[:, 0, 0] = co[:, 0]
    matrix[:, 0, 1] = -jsi[:, 0]

    matrix[:, 1, 0] = -jsi[:, 0]
    matrix[:, 1, 1] = co[:, 0]

    matrix[:, 2, 2] = co[:, 0]
    matrix[:, 2, 3] = jsi[:, 0]

    matrix[:, 3, 2] = jsi[:, 0]
    matrix[:, 3, 3] = co[:, 0]

    return matrix.squeeze(0)


def crx_matrix(params):
    """Compute unitary matrix for CRX gate.

    Args:
        params (torch.Tensor): The rotation angle.

    Returns:
        torch.Tensor: The computed unitary matrix.

    """
    theta = params.type(C_DTYPE)
    co = torch.cos(theta / 2)
    jsi = 1j * torch.sin(-theta / 2)

    matrix = (
        torch.tensor(
            [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]],
            dtype=C_DTYPE,
            device=params.device,
        )
        .unsqueeze(0)
        .repeat(co.shape[0], 1, 1)
    )
    matrix[:, 2, 2] = co[:, 0]
    matrix[:, 2, 3] = jsi[:, 0]
    matrix[:, 3, 2] = jsi[:, 0]
    matrix[:, 3, 3] = co[:, 0]

    return matrix.squeeze(0)


def cry_matrix(params):
    """Compute unitary matrix for CRY gate.

    Args:
        params (torch.Tensor): The rotation angle.

    Returns:
        torch.Tensor: The computed unitary matrix.

    """
    theta = params.type(C_DTYPE)
    co = torch.cos(theta / 2)
    si = torch.sin(theta / 2)

    matrix = (
        torch.tensor(
            [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]],
            dtype=C_DTYPE,
            device=params.device,
        )
        .unsqueeze(0)
        .repeat(co.shape[0], 1, 1)
    )
    matrix[:, 2, 2] = co[:, 0]
    matrix[:, 2, 3] = -si[:, 0]
    matrix[:, 3, 2] = si[:, 0]
    matrix[:, 3, 3] = co[:, 0]

    return matrix.squeeze(0)


def crz_matrix(params):
    """Compute unitary matrix for CRZ gate.

    Args:
        params (torch.Tensor): The rotation angle.

    Returns:
        torch.Tensor: The computed unitary matrix.

    """
    theta = params.type(C_DTYPE)
    exp = torch.exp(-0.5j * theta)

    matrix = (
        torch.tensor(
            [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]],
            dtype=C_DTYPE,
            device=params.device,
        )
        .unsqueeze(0)
        .repeat(exp.shape[0], 1, 1)
    )
    matrix[:, 2, 2] = exp[:, 0]
    matrix[:, 3, 3] = torch.conj(exp[:, 0])

    return matrix.squeeze(0)


def crot_matrix(params):
    """Compute unitary matrix for CRot gate.

    Args:
        params (torch.Tensor): The rotation angle.

    Returns:
        torch.Tensor: The computed unitary matrix.

    """
    phi = params[:, 0].type(C_DTYPE)
    theta = params[:, 1].type(C_DTYPE)
    omega = params[:, 2].type(C_DTYPE)

    co = torch.cos(theta / 2)
    si = torch.sin(theta / 2)

    matrix = (
        torch.tensor(
            [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]],
            dtype=C_DTYPE,
            device=params.device,
        )
        .unsqueeze(0)
        .repeat(phi.shape[0], 1, 1)
    )

    matrix[:, 2, 2] = torch.exp(-0.5j * (phi + omega)) * co
    matrix[:, 2, 3] = -torch.exp(0.5j * (phi - omega)) * si
    matrix[:, 3, 2] = torch.exp(-0.5j * (phi - omega)) * si
    matrix[:, 3, 3] = torch.exp(0.5j * (phi + omega)) * co

    return matrix.squeeze(0)


def u1_matrix(params):
    """Compute unitary matrix for U1 gate.

    Args:
        params (torch.Tensor): The rotation angle.

    Returns:
        torch.Tensor: The computed unitary matrix.

    """
    phi = params.type(C_DTYPE)
    exp = torch.exp(1j * phi)

    return torch.stack(
        [
            torch.cat(
                [
                    torch.ones(exp.shape, device=params.device),
                    torch.zeros(exp.shape, device=params.device),
                ],
                dim=-1,
            ),
            torch.cat([torch.zeros(exp.shape, device=params.device), exp], dim=-1),
        ],
        dim=-2,
    ).squeeze(0)


def cu_matrix(params):
    """Compute unitary matrix for CU gate.
    Args:
        params (torch.Tensor): The rotation angle.
    Returns:
        torch.Tensor: The computed unitary matrix.
    """
    theta = params[:, 0].unsqueeze(dim=-1).type(C_DTYPE)
    phi = params[:, 1].unsqueeze(dim=-1).type(C_DTYPE)
    lam = params[:, 2].unsqueeze(dim=-1).type(C_DTYPE)
    gamma = params[:, 3].unsqueeze(dim=-1).type(C_DTYPE)

    co = torch.cos(theta / 2)
    si = torch.sin(theta / 2)

    matrix = (
        torch.tensor(
            [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]],
            dtype=C_DTYPE,
            device=params.device,
        )
        .unsqueeze(0)
        .repeat(phi.shape[0], 1, 1)
    )

    matrix[:, 2, 2] = co * torch.exp(1j * gamma)
    matrix[:, 2, 3] = -si * torch.exp(1j * (lam + gamma))
    matrix[:, 3, 2] = si * torch.exp(1j * (phi + gamma))
    matrix[:, 3, 3] = co * torch.exp(1j * (phi + lam + gamma))

    return matrix.squeeze(0)


def cu1_matrix(params):
    """Compute unitary matrix for CU1 gate.

    Args:
        params (torch.Tensor): The rotation angle.

    Returns:
        torch.Tensor: The computed unitary matrix.

    """
    phi = params.type(C_DTYPE)
    exp = torch.exp(1j * phi)

    matrix = (
        torch.tensor(
            [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 0]],
            dtype=C_DTYPE,
            device=params.device,
        )
        .unsqueeze(0)
        .repeat(phi.shape[0], 1, 1)
    )

    matrix[:, 3, 3] = exp

    return matrix.squeeze(0)


def u2_matrix(params):
    """Compute unitary matrix for U2 gate.

    Args:
        params (torch.Tensor): The rotation angle.

    Returns:
        torch.Tensor: The computed unitary matrix.

    """
    phi = params[:, 0].unsqueeze(dim=-1).type(C_DTYPE)
    lam = params[:, 1].unsqueeze(dim=-1).type(C_DTYPE)

    return INV_SQRT2 * torch.stack(
        [
            torch.cat(
                [torch.ones(phi.shape, device=params.device), -torch.exp(1j * lam)],
                dim=-1,
            ),
            torch.cat([torch.exp(1j * phi), torch.exp(1j * (phi + lam))], dim=-1),
        ],
        dim=-2,
    ).squeeze(0)


def cu2_matrix(params):
    """Compute unitary matrix for CU2 gate.

    Args:
        params (torch.Tensor): The rotation angle.

    Returns:
        torch.Tensor: The computed unitary matrix.

    """
    phi = params[:, 0].unsqueeze(dim=-1).type(C_DTYPE)
    lam = params[:, 1].unsqueeze(dim=-1).type(C_DTYPE)

    matrix = (
        torch.tensor(
            [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 0]],
            dtype=C_DTYPE,
            device=params.device,
        )
        .unsqueeze(0)
        .repeat(phi.shape[0], 1, 1)
    )

    matrix[:, 2, 3] = -torch.exp(1j * lam)
    matrix[:, 3, 2] = torch.exp(1j * phi)
    matrix[:, 3, 3] = torch.exp(1j * (phi + lam))

    return matrix.squeeze(0)


def u3_matrix(params):
    """Compute unitary matrix for U3 gate.

    Args:
        params (torch.Tensor): The rotation angle.

    Returns:
        torch.Tensor: The computed unitary matrix.

    """
    theta = params[:, 0].unsqueeze(dim=-1).type(C_DTYPE)
    phi = params[:, 1].unsqueeze(dim=-1).type(C_DTYPE)
    lam = params[:, 2].unsqueeze(dim=-1).type(C_DTYPE)

    co = torch.cos(theta / 2)
    si = torch.sin(theta / 2)

    return torch.stack(
        [
            torch.cat([co, -si * torch.exp(1j * lam)], dim=-1),
            torch.cat(
                [si * torch.exp(1j * phi), co * torch.exp(1j * (phi + lam))], dim=-1
            ),
        ],
        dim=-2,
    ).squeeze(0)


def cu3_matrix(params):
    """Compute unitary matrix for CU3 gate.

    Args:
        params (torch.Tensor): The rotation angle.

    Returns:
        torch.Tensor: The computed unitary matrix.

    """
    theta = params[:, 0].unsqueeze(dim=-1).type(C_DTYPE)
    phi = params[:, 1].unsqueeze(dim=-1).type(C_DTYPE)
    lam = params[:, 2].unsqueeze(dim=-1).type(C_DTYPE)

    co = torch.cos(theta / 2)
    si = torch.sin(theta / 2)

    matrix = (
        torch.tensor(
            [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]],
            dtype=C_DTYPE,
            device=params.device,
        )
        .unsqueeze(0)
        .repeat(phi.shape[0], 1, 1)
    )

    matrix[:, 2, 2] = co
    matrix[:, 2, 3] = -si * torch.exp(1j * lam)
    matrix[:, 3, 2] = si * torch.exp(1j * phi)
    matrix[:, 3, 3] = co * torch.exp(1j * (phi + lam))

    return matrix.squeeze(0)


def kron(a, b):
    """Kronecker product of matrices a and b with leading batch dimensions.

    Batch dimensions are broadcast. The number of them mush.
    A part of the pylabyk library: numpytorch.py at https://github.com/yulkang/pylabyk

    :type a: torch.Tensor
    :type b: torch.Tensor
    :rtype: torch.Tensor
    """
    siz1 = torch.Size(torch.tensor(a.shape[-2:]) * torch.tensor(b.shape[-2:]))
    res = a.unsqueeze(-1).unsqueeze(-3) * b.unsqueeze(-2).unsqueeze(-4)
    siz0 = res.shape[:-4]
    return res.reshape(siz0 + siz1)


def su4_matrix(params):
    """Compute unitary matrix for SU(4) gate.

    A general two-qubit unitary is parameterized by 15 angles.
    We construct the full matrix using one- and two-qubit gates,
    based on Fig 2 of
    https://web.eecs.umich.edu/~imarkov/pubs/conf/spie04-2qubits.pdf

    Args:
        params (torch.Tensor): The rotation angles.

    Returns:
        torch.Tensor: The computed unitary matrix.
    """
    bsz = params.shape[0]
    zero = torch.zeros((bsz,1), device=params.device)
    one = torch.ones((bsz,1), device=params.device)

    # rotation angle for first Rz
    theta = params[:, 0].unsqueeze(dim=-1).type(C_DTYPE)

    # rotation angle for Rx
    phi = params[:, 1].unsqueeze(dim=-1).type(C_DTYPE)
    cos_of_phi = torch.cos(phi / 2)
    sin_of_phi = torch.sin(phi / 2)

    # rotation angle for second Rz
    lam = params[:, 2].unsqueeze(dim=-1).type(C_DTYPE)

    # SU(2) angles for gate a
    alpha1 = params[:, 3].unsqueeze(dim=-1).type(C_DTYPE)
    alpha2 = params[:, 4].unsqueeze(dim=-1).type(C_DTYPE)
    alpha3 = params[:, 5].unsqueeze(dim=-1).type(C_DTYPE)
    cos_of_alpha1 = torch.cos(alpha1 / 2)
    sin_of_alpha1 = torch.sin(alpha1 / 2)

    # SU(2) angles for gate b
    beta1 = params[:, 6].unsqueeze(dim=-1).type(C_DTYPE)
    beta2 = params[:, 7].unsqueeze(dim=-1).type(C_DTYPE)
    beta3 = params[:, 8].unsqueeze(dim=-1).type(C_DTYPE)
    cos_of_beta1 = torch.cos(beta1 / 2)
    sin_of_beta1 = torch.sin(beta1 / 2)

    # SU(2) angles for gate c
    gamma1 = params[:, 9].unsqueeze(dim=-1).type(C_DTYPE)
    gamma2 = params[:, 10].unsqueeze(dim=-1).type(C_DTYPE)
    gamma3 = params[:, 11].unsqueeze(dim=-1).type(C_DTYPE)
    cos_of_gamma1 = torch.cos(gamma1 / 2)
    sin_of_gamma1 = torch.sin(gamma1 / 2)

    # SU(2) angles for gate d
    delta1 = params[:, 12].unsqueeze(dim=-1).type(C_DTYPE)
    delta2 = params[:, 13].unsqueeze(dim=-1).type(C_DTYPE)
    delta3 = params[:, 14].unsqueeze(dim=-1).type(C_DTYPE)
    cos_of_delta1 = torch.cos(delta1 / 2)
    sin_of_delta1 = torch.sin(delta1 / 2)

    # Construct all one-qubit gates needed
    iden = torch.eye(2, device=params.device).repeat(bsz, 1, 1)

    rz1 = torch.stack(
        [
            torch.cat([torch.exp(-1j * theta / 2), zero], dim=-1),
            torch.cat([zero, torch.exp(1j * theta / 2)], dim=-1),
        ],
        dim=-2,
    )

    rz2 = torch.stack(
        [
            torch.cat([torch.exp(-1j * lam / 2), zero], dim=-1),
            torch.cat([zero, torch.exp(1j * lam / 2)], dim=-1),
        ],
        dim=-2,
    )

    rx1 = torch.stack(
        [
            torch.cat([cos_of_phi, -1j * sin_of_phi], dim=-1),
            torch.cat([-1j * sin_of_phi, cos_of_phi], dim=-1),
        ],
        dim=-2,
    )

    a_su2 = torch.stack(
        [
            torch.cat([cos_of_alpha1, -1 * torch.exp(1j * alpha3) * sin_of_alpha1], dim=-1),
            torch.cat([torch.exp(1j * alpha2) * sin_of_alpha1, torch.exp(1j * (alpha2 + alpha3)) * cos_of_alpha1], dim=-1),
        ],
        dim=-2,
    )

    b_su2 = torch.stack(
        [
            torch.cat([cos_of_beta1, -1 * torch.exp(1j * beta3) * sin_of_beta1], dim=-1),
            torch.cat([torch.exp(1j * beta2) * sin_of_beta1, torch.exp(1j * (beta2 + beta3)) * cos_of_beta1], dim=-1),
        ],
        dim=-2,
    )

    c_su2 = torch.stack(
        [
            torch.cat([cos_of_gamma1, -1 * torch.exp(1j * gamma3) * sin_of_gamma1], dim=-1),
            torch.cat([torch.exp(1j * gamma2) * sin_of_gamma1, torch.exp(1j * (gamma2 + gamma3)) * cos_of_gamma1], dim=-1),
        ],
        dim=-2,
    )

    d_su2 = torch.stack(
        [
            torch.cat([cos_of_delta1, -1 * torch.exp(1j * delta3) * sin_of_delta1], dim=-1),
            torch.cat([torch.exp(1j * delta2) * sin_of_delta1, torch.exp(1j * (delta2 + delta3)) * cos_of_delta1], dim=-1),
        ],
        dim=-2,
    )

    # Construct two-qubit CNOT
    cnot = torch.stack(
        [
            torch.cat([one, zero, zero, zero], dim=-1),
            torch.cat([zero, one, zero, zero], dim=-1),
            torch.cat([zero, zero, zero, one], dim=-1),
            torch.cat([zero, zero, one, zero], dim=-1),
        ],
        dim=-2,
    ).type(C_DTYPE)

    matrix = torch.bmm(cnot, kron(iden, rz1))
    matrix = torch.bmm(kron(c_su2, d_su2), matrix)
    matrix = torch.bmm(cnot, matrix)
    matrix = torch.bmm(kron(rx1, rz2), matrix)
    matrix = torch.bmm(cnot, matrix)
    return torch.bmm(kron(a_su2, b_su2), matrix).squeeze(0)


def qubitunitary_matrix(params):
    """Compute unitary matrix for Qubitunitary gate.

    Args:
        params (torch.Tensor): The unitary matrix.

    Returns:
        torch.Tensor: The computed unitary matrix.

    """
    matrix = params.squeeze(0)
    try:
        assert matrix.shape[-1] == matrix.shape[-2]
    except AssertionError as err:
        logger.exception(f"Operator must be a square matrix.")
        raise err

    try:
        U = matrix.cpu().detach().numpy()
        if matrix.dim() > 2:
            # batched unitary
            bsz = matrix.shape[0]
            assert np.allclose(
                np.matmul(U, np.transpose(U.conj(), [0, 2, 1])),
                np.stack([np.identity(U.shape[-1])] * bsz),
                atol=1e-5,
            )
        else:
            assert np.allclose(
                np.matmul(U, np.transpose(U.conj(), [1, 0])),
                np.identity(U.shape[0]),
                atol=1e-5,
            )
    except AssertionError as err:
        logger.exception(f"Operator must be unitary.")
        raise err

    return matrix


def qubitunitaryfast_matrix(params):
    """Compute unitary matrix for Qubitunitary fast gate.

    Args:
        params (torch.Tensor): The unitary matrix.

    Returns:
        torch.Tensor: The computed unitary matrix.

    """
    return params.squeeze(0)


def qubitunitarystrict_matrix(params):
    """Compute unitary matrix for Qubitunitary strict gate.
        Strictly be the unitary.

    Args:
        params (torch.Tensor): The unitary matrix.

    Returns:
        torch.Tensor: The computed unitary matrix.

    """
    params.squeeze(0)
    mat = params
    U, Sigma, V = torch.svd(mat)
    return U.matmul(V)


def multicnot_matrix(n_wires):
    """Compute unitary matrix for Multi qubit CNOT gate.

    Args:
        n_wires (int): The number of wires.

    Returns:
        torch.Tensor: The computed unitary matrix.

    """
    mat = torch.eye(2**n_wires, dtype=C_DTYPE)
    mat[-1][-1] = 0
    mat[-2][-2] = 0
    mat[-1][-2] = 1
    mat[-2][-1] = 1

    return mat


def multixcnot_matrix(n_wires):
    """Compute unitary matrix for Multi qubit XCNOT gate.

    Args:
        params (torch.Tensor): The unitary matrix.

    Returns:
        torch.Tensor: The computed unitary matrix.

    """
    # when all control qubits are zero, then the target qubit will flip
    mat = torch.eye(2**n_wires, dtype=C_DTYPE)
    mat[0][0] = 0
    mat[1][1] = 0
    mat[0][1] = 1
    mat[1][0] = 1

    return mat


def singleexcitation_matrix(params):
    """Compute unitary matrix for single excitation gate.

    Args:
        params (torch.Tensor): The rotation angle.

    Returns:
        torch.Tensor: The computed unitary matrix.

    """
    theta = params.type(C_DTYPE)
    co = torch.cos(theta / 2)
    si = torch.sin(theta / 2)

    matrix = (
        torch.tensor(
            [[1, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 1]],
            dtype=C_DTYPE,
            device=params.device,
        )
        .unsqueeze(0)
        .repeat(theta.shape[0], 1, 1)
    )

    matrix[:, 1, 1] = co
    matrix[:, 1, 2] = -si
    matrix[:, 2, 1] = si
    matrix[:, 2, 2] = co

    return matrix.squeeze(0)


def qft_matrix(n_wires):
    """Compute unitary matrix for QFT.

    Args:
        n_wires: the number of qubits
    """
    dimension = 2**n_wires
    mat = torch.zeros((dimension, dimension), dtype=torch.complex64)
    omega = np.exp(2 * np.pi * 1j / dimension)

    for m in range(dimension):
        for n in range(dimension):
            mat[m, n] = omega ** (m * n)
    mat = mat / np.sqrt(dimension)
    return mat


def r_matrix(params: torch.Tensor) -> torch.Tensor:
    """Compute unitary matrix for R gate.

    Args:
        params (torch.Tensor): The rotation angle.

    Returns:
        torch.Tensor: The computed unitary matrix.

    """

    theta = params[:, 0].unsqueeze(dim=-1).type(C_DTYPE)
    phi = params[:, 1].unsqueeze(dim=-1).type(C_DTYPE)
    exp = torch.exp(-1j * phi)
    """
    Seems to be a pytorch bug. Have to explicitly cast the theta to a
    complex number. If directly theta = params, then get error:

    allow_unreachable=True, accumulate_grad=True)  # allow_unreachable flag
    RuntimeError: Expected isFloatingType(grad.scalar_type()) ||
    (input_is_complex == grad_is_complex) to be true, but got false.
    (Could this error message be improved?
    If so, please report an enhancement request to PyTorch.)

    """
    co = torch.cos(theta / 2)
    jsi = 1j * torch.sin(-theta / 2)

    return torch.stack(
        [
            torch.cat([co, exp * jsi], dim=-1),
            torch.cat([torch.conj(exp) * jsi, co], dim=-1),
        ],
        dim=-2,
    ).squeeze(0)


def globalphase_matrix(params):
    """Compute unitary matrix for Multi qubit XCNOT gate.
    Args:
        params (torch.Tensor): The phase.
    Returns:
        torch.Tensor: The computed unitary matrix.
    """
    phase = params.type(C_DTYPE)
    exp = torch.exp(1j * phase)
    matrix = torch.tensor([[exp]], dtype=C_DTYPE, device=params.device)

    return matrix


def c3x_matrix():
    """Compute unitary matrix for C3X.
    Args:
        None
    Returns:
        torch.Tensor: The computed unitary matrix.
    """

    mat = torch.eye(16, dtype=C_DTYPE)
    mat[15][15] = 0
    mat[14][14] = 0
    mat[15][14] = 1
    mat[14][15] = 1

    return mat


def c4x_matrix():
    """Compute unitary matrix for C4X gate.
    Args:
        None
    Returns:
        torch.Tensor: The computed unitary matrix.
    """
    mat = torch.eye(32, dtype=C_DTYPE)
    mat[30][30] = 0
    mat[30][31] = 1
    mat[31][31] = 0
    mat[31][30] = 1

    return mat


def c3sx_matrix():
    """Compute unitary matrix for c3sx gate.
    Args:
        None.
    Returns:
        torch.Tensor: The computed unitary matrix.
    """
    mat = torch.eye(16, dtype=C_DTYPE)
    mat[14][14] = (1 + 1j) / 2
    mat[14][15] = (1 - 1j) / 2
    mat[15][14] = (1 - 1j) / 2
    mat[15][15] = (1 + 1j) / 2

    return mat


mat_dict = {
    "hadamard": torch.tensor(
        [[INV_SQRT2, INV_SQRT2], [INV_SQRT2, -INV_SQRT2]], dtype=C_DTYPE
    ),
    "shadamard": torch.tensor(
        [
            [np.cos(np.pi / 8), -np.sin(np.pi / 8)],
            [np.sin(np.pi / 8), np.cos(np.pi / 8)],
        ],
        dtype=C_DTYPE,
    ),
    "paulix": torch.tensor([[0, 1], [1, 0]], dtype=C_DTYPE),
    "pauliy": torch.tensor([[0, -1j], [1j, 0]], dtype=C_DTYPE),
    "pauliz": torch.tensor([[1, 0], [0, -1]], dtype=C_DTYPE),
    "i": torch.tensor([[1, 0], [0, 1]], dtype=C_DTYPE),
    "s": torch.tensor([[1, 0], [0, 1j]], dtype=C_DTYPE),
    "t": torch.tensor([[1, 0], [0, np.exp(1j * np.pi / 4)]], dtype=C_DTYPE),
    "sx": 0.5 * torch.tensor([[1 + 1j, 1 - 1j], [1 - 1j, 1 + 1j]], dtype=C_DTYPE),
    "cnot": torch.tensor(
        [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 0, 1], [0, 0, 1, 0]], dtype=C_DTYPE
    ),
    "cz": torch.tensor(
        [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, -1]], dtype=C_DTYPE
    ),
    "cy": torch.tensor(
        [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 0, -1j], [0, 0, 1j, 0]], dtype=C_DTYPE
    ),
    "swap": torch.tensor(
        [[1, 0, 0, 0], [0, 0, 1, 0], [0, 1, 0, 0], [0, 0, 0, 1]], dtype=C_DTYPE
    ),
    "sswap": torch.tensor(
        [
            [1, 0, 0, 0],
            [0, (1 + 1j) / 2, (1 - 1j) / 2, 0],
            [0, (1 - 1j) / 2, (1 + 1j) / 2, 0],
            [0, 0, 0, 1],
        ],
        dtype=C_DTYPE,
    ),
    "cswap": torch.tensor(
        [
            [1, 0, 0, 0, 0, 0, 0, 0],
            [0, 1, 0, 0, 0, 0, 0, 0],
            [0, 0, 1, 0, 0, 0, 0, 0],
            [0, 0, 0, 1, 0, 0, 0, 0],
            [0, 0, 0, 0, 1, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 1, 0],
            [0, 0, 0, 0, 0, 1, 0, 0],
            [0, 0, 0, 0, 0, 0, 0, 1],
        ],
        dtype=C_DTYPE,
    ),
    "toffoli": torch.tensor(
        [
            [1, 0, 0, 0, 0, 0, 0, 0],
            [0, 1, 0, 0, 0, 0, 0, 0],
            [0, 0, 1, 0, 0, 0, 0, 0],
            [0, 0, 0, 1, 0, 0, 0, 0],
            [0, 0, 0, 0, 1, 0, 0, 0],
            [0, 0, 0, 0, 0, 1, 0, 0],
            [0, 0, 0, 0, 0, 0, 0, 1],
            [0, 0, 0, 0, 0, 0, 1, 0],
        ],
        dtype=C_DTYPE,
    ),
    "ecr": INV_SQRT2
    * torch.tensor(
        [[0, 0, 1, 1j], [0, 0, 1j, 1], [1, -1j, 0, 0], [-1j, 1, 0, 0]], dtype=C_DTYPE
    ),
    "sdg": torch.tensor([[1, 0], [0, -1j]], dtype=C_DTYPE),
    "tdg": torch.tensor([[1, 0], [0, np.exp(-1j * np.pi / 4)]], dtype=C_DTYPE),
    "sxdg": torch.tensor(
        [[0.5 - 0.5j, 0.5 + 0.5j], [0.5 + 0.5j, 0.5 - 0.5j]], dtype=C_DTYPE
    ),
    "chadamard": torch.tensor(
        [
            [1, 0, 0, 0],
            [0, 1, 0, 0],
            [0, 0, INV_SQRT2, INV_SQRT2],
            [0, 0, INV_SQRT2, -INV_SQRT2],
        ],
        dtype=C_DTYPE,
    ),
    "iswap": torch.tensor(
        [[1, 0, 0, 0], [0, 0, 1j, 0], [0, 1j, 0, 0], [0, 0, 0, 1]], dtype=C_DTYPE
    ),
    "ccz": torch.tensor(
        [
            [1, 0, 0, 0, 0, 0, 0, 0],
            [0, 1, 0, 0, 0, 0, 0, 0],
            [0, 0, 1, 0, 0, 0, 0, 0],
            [0, 0, 0, 1, 0, 0, 0, 0],
            [0, 0, 0, 0, 1, 0, 0, 0],
            [0, 0, 0, 0, 0, 1, 0, 0],
            [0, 0, 0, 0, 0, 0, 1, 0],
            [0, 0, 0, 0, 0, 0, 0, -1],
        ],
        dtype=C_DTYPE,
    ),
    "cs": torch.tensor(
        [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1j]], dtype=C_DTYPE
    ),
    "csdg": torch.tensor(
        [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, -1j]], dtype=C_DTYPE
    ),
    "csx": torch.tensor(
        [
            [1, 0, 0, 0],
            [0, 1, 0, 0],
            [0, 0, 0.5 + 0.5j, 0.5 - 0.5j],
            [0, 0, 0.5 - 0.5j, 0.5 + 0.5j],
        ],
        dtype=C_DTYPE,
    ),
    "rx": rx_matrix,
    "ry": ry_matrix,
    "rz": rz_matrix,
    "rxx": rxx_matrix,
    "ryy": ryy_matrix,
    "rzz": rzz_matrix,
    "rzx": rzx_matrix,
    "phaseshift": phaseshift_matrix,
    "rot": rot_matrix,
    "multirz": multirz_matrix,
    "crx": crx_matrix,
    "cry": cry_matrix,
    "crz": crz_matrix,
    "crot": crot_matrix,
    "u1": u1_matrix,
    "u2": u2_matrix,
    "u3": u3_matrix,
    "cu": cu_matrix,
    "cu1": cu1_matrix,
    "cu2": cu2_matrix,
    "cu3": cu3_matrix,
    "su4": su4_matrix,
    "qubitunitary": qubitunitary_matrix,
    "qubitunitaryfast": qubitunitaryfast_matrix,
    "qubitunitarystrict": qubitunitarystrict_matrix,
    "multicnot": multicnot_matrix,
    "multixcnot": multixcnot_matrix,
    "singleexcitation": singleexcitation_matrix,
    "qft": qft_matrix,
    "dcx": torch.tensor(
        [[1, 0, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1], [0, 1, 0, 0]], dtype=C_DTYPE
    ),
    "xxminyy": xxminyy_matrix,
    "xxplusyy": xxplusyy_matrix,
    "r": r_matrix,
    "globalphase": globalphase_matrix,
    "c3x": c3x_matrix(),
    "c4x": c4x_matrix(),
    "c3sx": c3sx_matrix(),
    "rccx": torch.tensor(
        [
            [1, 0, 0, 0, 0, 0, 0, 0],
            [0, 1, 0, 0, 0, 0, 0, 0],
            [0, 0, 1, 0, 0, 0, 0, 0],
            [0, 0, 0, 1, 0, 0, 0, 0],
            [0, 0, 0, 0, 1, 0, 0, 0],
            [0, 0, 0, 0, 0, -1, 0, 0],
            [0, 0, 0, 0, 0, 0, 0, -1j],
            [0, 0, 0, 0, 0, 0, 1j, 0],
        ],
        dtype=C_DTYPE,
    ),
    "rc3x": torch.tensor(
        [
            [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            [0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            [0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            [0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1j, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, -1j, 0, 0],
            [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1],
            [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, -1, 0],
        ],
        dtype=C_DTYPE,
    ),
}


def hadamard(
    q_device: QuantumDevice,
    wires: Union[List[int], int],
    params: torch.Tensor = None,
    n_wires: int = None,
    static: bool = False,
    parent_graph=None,
    inverse: bool = False,
    comp_method: str = "bmm",
):
    """Perform the hadamard gate.

    Args:
        q_device (tq.QuantumDevice): The QuantumDevice.
        wires (Union[List[int], int]): Which qubit(s) to apply the gate.
        params (torch.Tensor, optional): Parameters (if any) of the gate.
            Default to None.
        n_wires (int, optional): Number of qubits the gate is applied to.
            Default to None.
        static (bool, optional): Whether use static mode computation.
            Default to False.
        parent_graph (tq.QuantumGraph, optional): Parent QuantumGraph of
            current operation. Default to None.
        inverse (bool, optional): Whether inverse the gate. Default to False.
        comp_method (bool, optional): Use 'bmm' or 'einsum' method to perform
        matrix vector multiplication. Default to 'bmm'.

    Returns:
        None.

    """
    name = "hadamard"
    mat = mat_dict[name]
    gate_wrapper(
        name=name,
        mat=mat,
        method=comp_method,
        q_device=q_device,
        wires=wires,
        params=params,
        n_wires=n_wires,
        static=static,
        parent_graph=parent_graph,
        inverse=inverse,
    )


def shadamard(
    q_device,
    wires,
    params=None,
    n_wires=None,
    static=False,
    parent_graph=None,
    inverse=False,
    comp_method="bmm",
):
    """Perform the shadamard gate.

    Args:
        q_device (tq.QuantumDevice): The QuantumDevice.
        wires (Union[List[int], int]): Which qubit(s) to apply the gate.
        params (torch.Tensor, optional): Parameters (if any) of the gate.
            Default to None.
        n_wires (int, optional): Number of qubits the gate is applied to.
            Default to None.
        static (bool, optional): Whether use static mode computation.
            Default to False.
        parent_graph (tq.QuantumGraph, optional): Parent QuantumGraph of
            current operation. Default to None.
        inverse (bool, optional): Whether inverse the gate. Default to False.
        comp_method (bool, optional): Use 'bmm' or 'einsum' method to perform
        matrix vector multiplication. Default to 'bmm'.

    Returns:
        None.

    """
    name = "shadamard"
    mat = mat_dict[name]
    gate_wrapper(
        name=name,
        mat=mat,
        method=comp_method,
        q_device=q_device,
        wires=wires,
        params=params,
        n_wires=n_wires,
        static=static,
        parent_graph=parent_graph,
        inverse=inverse,
    )


def paulix(
    q_device,
    wires,
    params=None,
    n_wires=None,
    static=False,
    parent_graph=None,
    inverse=False,
    comp_method="bmm",
):
    """Perform the Pauli X gate.

    Args:
        q_device (tq.QuantumDevice): The QuantumDevice.
        wires (Union[List[int], int]): Which qubit(s) to apply the gate.
        params (torch.Tensor, optional): Parameters (if any) of the gate.
            Default to None.
        n_wires (int, optional): Number of qubits the gate is applied to.
            Default to None.
        static (bool, optional): Whether use static mode computation.
            Default to False.
        parent_graph (tq.QuantumGraph, optional): Parent QuantumGraph of
            current operation. Default to None.
        inverse (bool, optional): Whether inverse the gate. Default to False.
        comp_method (bool, optional): Use 'bmm' or 'einsum' method to perform
        matrix vector multiplication. Default to 'bmm'.

    Returns:
        None.

    """
    name = "paulix"
    mat = mat_dict[name]
    gate_wrapper(
        name=name,
        mat=mat,
        method=comp_method,
        q_device=q_device,
        wires=wires,
        params=params,
        n_wires=n_wires,
        static=static,
        parent_graph=parent_graph,
        inverse=inverse,
    )


def pauliy(
    q_device,
    wires,
    params=None,
    n_wires=None,
    static=False,
    parent_graph=None,
    inverse=False,
    comp_method="bmm",
):
    """Perform the Pauli Y gate.

    Args:
        q_device (tq.QuantumDevice): The QuantumDevice.
        wires (Union[List[int], int]): Which qubit(s) to apply the gate.
        params (torch.Tensor, optional): Parameters (if any) of the gate.
            Default to None.
        n_wires (int, optional): Number of qubits the gate is applied to.
            Default to None.
        static (bool, optional): Whether use static mode computation.
            Default to False.
        parent_graph (tq.QuantumGraph, optional): Parent QuantumGraph of
            current operation. Default to None.
        inverse (bool, optional): Whether inverse the gate. Default to False.
        comp_method (bool, optional): Use 'bmm' or 'einsum' method to perform
        matrix vector multiplication. Default to 'bmm'.

    Returns:
        None.

    """
    name = "pauliy"
    mat = mat_dict[name]
    gate_wrapper(
        name=name,
        mat=mat,
        method=comp_method,
        q_device=q_device,
        wires=wires,
        params=params,
        n_wires=n_wires,
        static=static,
        parent_graph=parent_graph,
        inverse=inverse,
    )


def pauliz(
    q_device,
    wires,
    params=None,
    n_wires=None,
    static=False,
    parent_graph=None,
    inverse=False,
    comp_method="bmm",
):
    """Perform the Pauli Z gate.

    Args:
        q_device (tq.QuantumDevice): The QuantumDevice.
        wires (Union[List[int], int]): Which qubit(s) to apply the gate.
        params (torch.Tensor, optional): Parameters (if any) of the gate.
            Default to None.
        n_wires (int, optional): Number of qubits the gate is applied to.
            Default to None.
        static (bool, optional): Whether use static mode computation.
            Default to False.
        parent_graph (tq.QuantumGraph, optional): Parent QuantumGraph of
            current operation. Default to None.
        inverse (bool, optional): Whether inverse the gate. Default to False.
        comp_method (bool, optional): Use 'bmm' or 'einsum' method to perform
        matrix vector multiplication. Default to 'bmm'.

    Returns:
        None.

    """
    name = "pauliz"
    mat = mat_dict[name]
    gate_wrapper(
        name=name,
        mat=mat,
        method=comp_method,
        q_device=q_device,
        wires=wires,
        params=params,
        n_wires=n_wires,
        static=static,
        parent_graph=parent_graph,
        inverse=inverse,
    )


def i(
    q_device,
    wires,
    params=None,
    n_wires=None,
    static=False,
    parent_graph=None,
    inverse=False,
    comp_method="bmm",
):
    """Perform the I gate.

    Args:
        q_device (tq.QuantumDevice): The QuantumDevice.
        wires (Union[List[int], int]): Which qubit(s) to apply the gate.
        params (torch.Tensor, optional): Parameters (if any) of the gate.
            Default to None.
        n_wires (int, optional): Number of qubits the gate is applied to.
            Default to None.
        static (bool, optional): Whether use static mode computation.
            Default to False.
        parent_graph (tq.QuantumGraph, optional): Parent QuantumGraph of
            current operation. Default to None.
        inverse (bool, optional): Whether inverse the gate. Default to False.
        comp_method (bool, optional): Use 'bmm' or 'einsum' method to perform
        matrix vector multiplication. Default to 'bmm'.

    Returns:
        None.

    """
    name = "i"
    mat = mat_dict[name]
    gate_wrapper(
        name=name,
        mat=mat,
        method=comp_method,
        q_device=q_device,
        wires=wires,
        params=params,
        n_wires=n_wires,
        static=static,
        parent_graph=parent_graph,
        inverse=inverse,
    )


def s(
    q_device,
    wires,
    params=None,
    n_wires=None,
    static=False,
    parent_graph=None,
    inverse=False,
    comp_method="bmm",
):
    """Perform the s gate.

    Args:
        q_device (tq.QuantumDevice): The QuantumDevice.
        wires (Union[List[int], int]): Which qubit(s) to apply the gate.
        params (torch.Tensor, optional): Parameters (if any) of the gate.
            Default to None.
        n_wires (int, optional): Number of qubits the gate is applied to.
            Default to None.
        static (bool, optional): Whether use static mode computation.
            Default to False.
        parent_graph (tq.QuantumGraph, optional): Parent QuantumGraph of
            current operation. Default to None.
        inverse (bool, optional): Whether inverse the gate. Default to False.
        comp_method (bool, optional): Use 'bmm' or 'einsum' method to perform
        matrix vector multiplication. Default to 'bmm'.

    Returns:
        None.

    """
    name = "s"
    mat = mat_dict[name]
    gate_wrapper(
        name=name,
        mat=mat,
        method=comp_method,
        q_device=q_device,
        wires=wires,
        params=params,
        n_wires=n_wires,
        static=static,
        parent_graph=parent_graph,
        inverse=inverse,
    )


def t(
    q_device,
    wires,
    params=None,
    n_wires=None,
    static=False,
    parent_graph=None,
    inverse=False,
    comp_method="bmm",
):
    """Perform the t gate.

    Args:
        q_device (tq.QuantumDevice): The QuantumDevice.
        wires (Union[List[int], int]): Which qubit(s) to apply the gate.
        params (torch.Tensor, optional): Parameters (if any) of the gate.
            Default to None.
        n_wires (int, optional): Number of qubits the gate is applied to.
            Default to None.
        static (bool, optional): Whether use static mode computation.
            Default to False.
        parent_graph (tq.QuantumGraph, optional): Parent QuantumGraph of
            current operation. Default to None.
        inverse (bool, optional): Whether inverse the gate. Default to False.
        comp_method (bool, optional): Use 'bmm' or 'einsum' method to perform
        matrix vector multiplication. Default to 'bmm'.

    Returns:
        None.

    """
    name = "t"
    mat = mat_dict[name]
    gate_wrapper(
        name=name,
        mat=mat,
        method=comp_method,
        q_device=q_device,
        wires=wires,
        params=params,
        n_wires=n_wires,
        static=static,
        parent_graph=parent_graph,
        inverse=inverse,
    )


def sx(
    q_device,
    wires,
    params=None,
    n_wires=None,
    static=False,
    parent_graph=None,
    inverse=False,
    comp_method="bmm",
):
    """Perform the sx gate.

    Args:
        q_device (tq.QuantumDevice): The QuantumDevice.
        wires (Union[List[int], int]): Which qubit(s) to apply the gate.
        params (torch.Tensor, optional): Parameters (if any) of the gate.
            Default to None.
        n_wires (int, optional): Number of qubits the gate is applied to.
            Default to None.
        static (bool, optional): Whether use static mode computation.
            Default to False.
        parent_graph (tq.QuantumGraph, optional): Parent QuantumGraph of
            current operation. Default to None.
        inverse (bool, optional): Whether inverse the gate. Default to False.
        comp_method (bool, optional): Use 'bmm' or 'einsum' method to perform
        matrix vector multiplication. Default to 'bmm'.

    Returns:
        None.

    """
    name = "sx"
    mat = mat_dict[name]
    gate_wrapper(
        name=name,
        mat=mat,
        method=comp_method,
        q_device=q_device,
        wires=wires,
        params=params,
        n_wires=n_wires,
        static=static,
        parent_graph=parent_graph,
        inverse=inverse,
    )


def cnot(
    q_device,
    wires,
    params=None,
    n_wires=None,
    static=False,
    parent_graph=None,
    inverse=False,
    comp_method="bmm",
):
    """Perform the cnot gate.

    Args:
        q_device (tq.QuantumDevice): The QuantumDevice.
        wires (Union[List[int], int]): Which qubit(s) to apply the gate.
        params (torch.Tensor, optional): Parameters (if any) of the gate.
            Default to None.
        n_wires (int, optional): Number of qubits the gate is applied to.
            Default to None.
        static (bool, optional): Whether use static mode computation.
            Default to False.
        parent_graph (tq.QuantumGraph, optional): Parent QuantumGraph of
            current operation. Default to None.
        inverse (bool, optional): Whether inverse the gate. Default to False.
        comp_method (bool, optional): Use 'bmm' or 'einsum' method to perform
        matrix vector multiplication. Default to 'bmm'.

    Returns:
        None.

    """
    name = "cnot"
    mat = mat_dict[name]
    gate_wrapper(
        name=name,
        mat=mat,
        method=comp_method,
        q_device=q_device,
        wires=wires,
        params=params,
        n_wires=n_wires,
        static=static,
        parent_graph=parent_graph,
        inverse=inverse,
    )


def cz(
    q_device,
    wires,
    params=None,
    n_wires=None,
    static=False,
    parent_graph=None,
    inverse=False,
    comp_method="bmm",
):
    """Perform the cz gate.

    Args:
        q_device (tq.QuantumDevice): The QuantumDevice.
        wires (Union[List[int], int]): Which qubit(s) to apply the gate.
        params (torch.Tensor, optional): Parameters (if any) of the gate.
            Default to None.
        n_wires (int, optional): Number of qubits the gate is applied to.
            Default to None.
        static (bool, optional): Whether use static mode computation.
            Default to False.
        parent_graph (tq.QuantumGraph, optional): Parent QuantumGraph of
            current operation. Default to None.
        inverse (bool, optional): Whether inverse the gate. Default to False.
        comp_method (bool, optional): Use 'bmm' or 'einsum' method to perform
        matrix vector multiplication. Default to 'bmm'.

    Returns:
        None.

    """
    name = "cz"
    mat = mat_dict[name]
    gate_wrapper(
        name=name,
        mat=mat,
        method=comp_method,
        q_device=q_device,
        wires=wires,
        params=params,
        n_wires=n_wires,
        static=static,
        parent_graph=parent_graph,
        inverse=inverse,
    )


def cy(
    q_device,
    wires,
    params=None,
    n_wires=None,
    static=False,
    parent_graph=None,
    inverse=False,
    comp_method="bmm",
):
    """Perform the cy gate.

    Args:
        q_device (tq.QuantumDevice): The QuantumDevice.
        wires (Union[List[int], int]): Which qubit(s) to apply the gate.
        params (torch.Tensor, optional): Parameters (if any) of the gate.
            Default to None.
        n_wires (int, optional): Number of qubits the gate is applied to.
            Default to None.
        static (bool, optional): Whether use static mode computation.
            Default to False.
        parent_graph (tq.QuantumGraph, optional): Parent QuantumGraph of
            current operation. Default to None.
        inverse (bool, optional): Whether inverse the gate. Default to False.
        comp_method (bool, optional): Use 'bmm' or 'einsum' method to perform
        matrix vector multiplication. Default to 'bmm'.

    Returns:
        None.

    """
    name = "cy"
    mat = mat_dict[name]
    gate_wrapper(
        name=name,
        mat=mat,
        method=comp_method,
        q_device=q_device,
        wires=wires,
        params=params,
        n_wires=n_wires,
        static=static,
        parent_graph=parent_graph,
        inverse=inverse,
    )


def rx(
    q_device,
    wires,
    params=None,
    n_wires=None,
    static=False,
    parent_graph=None,
    inverse=False,
    comp_method="bmm",
):
    """Perform the rx gate.

    Args:
        q_device (tq.QuantumDevice): The QuantumDevice.
        wires (Union[List[int], int]): Which qubit(s) to apply the gate.
        params (torch.Tensor, optional): Parameters (if any) of the gate.
            Default to None.
        n_wires (int, optional): Number of qubits the gate is applied to.
            Default to None.
        static (bool, optional): Whether use static mode computation.
            Default to False.
        parent_graph (tq.QuantumGraph, optional): Parent QuantumGraph of
            current operation. Default to None.
        inverse (bool, optional): Whether inverse the gate. Default to False.
        comp_method (bool, optional): Use 'bmm' or 'einsum' method to perform
        matrix vector multiplication. Default to 'bmm'.

    Returns:
        None.

    """
    name = "rx"
    mat = mat_dict[name]
    gate_wrapper(
        name=name,
        mat=mat,
        method=comp_method,
        q_device=q_device,
        wires=wires,
        params=params,
        n_wires=n_wires,
        static=static,
        parent_graph=parent_graph,
        inverse=inverse,
    )


def ry(
    q_device,
    wires,
    params=None,
    n_wires=None,
    static=False,
    parent_graph=None,
    inverse=False,
    comp_method="bmm",
):
    """Perform the ry gate.

    Args:
        q_device (tq.QuantumDevice): The QuantumDevice.
        wires (Union[List[int], int]): Which qubit(s) to apply the gate.
        params (torch.Tensor, optional): Parameters (if any) of the gate.
            Default to None.
        n_wires (int, optional): Number of qubits the gate is applied to.
            Default to None.
        static (bool, optional): Whether use static mode computation.
            Default to False.
        parent_graph (tq.QuantumGraph, optional): Parent QuantumGraph of
            current operation. Default to None.
        inverse (bool, optional): Whether inverse the gate. Default to False.
        comp_method (bool, optional): Use 'bmm' or 'einsum' method to perform
        matrix vector multiplication. Default to 'bmm'.

    Returns:
        None.

    """
    name = "ry"
    mat = mat_dict[name]
    gate_wrapper(
        name=name,
        mat=mat,
        method=comp_method,
        q_device=q_device,
        wires=wires,
        params=params,
        n_wires=n_wires,
        static=static,
        parent_graph=parent_graph,
        inverse=inverse,
    )


def rz(
    q_device,
    wires,
    params=None,
    n_wires=None,
    static=False,
    parent_graph=None,
    inverse=False,
    comp_method="bmm",
):
    """Perform the rz gate.

    Args:
        q_device (tq.QuantumDevice): The QuantumDevice.
        wires (Union[List[int], int]): Which qubit(s) to apply the gate.
        params (torch.Tensor, optional): Parameters (if any) of the gate.
            Default to None.
        n_wires (int, optional): Number of qubits the gate is applied to.
            Default to None.
        static (bool, optional): Whether use static mode computation.
            Default to False.
        parent_graph (tq.QuantumGraph, optional): Parent QuantumGraph of
            current operation. Default to None.
        inverse (bool, optional): Whether inverse the gate. Default to False.
        comp_method (bool, optional): Use 'bmm' or 'einsum' method to perform
        matrix vector multiplication. Default to 'bmm'.

    Returns:
        None.

    """
    name = "rz"
    mat = mat_dict[name]
    gate_wrapper(
        name=name,
        mat=mat,
        method=comp_method,
        q_device=q_device,
        wires=wires,
        params=params,
        n_wires=n_wires,
        static=static,
        parent_graph=parent_graph,
        inverse=inverse,
    )


def rxx(
    q_device,
    wires,
    params=None,
    n_wires=None,
    static=False,
    parent_graph=None,
    inverse=False,
    comp_method="bmm",
):
    """Perform the rxx gate.

    Args:
        q_device (tq.QuantumDevice): The QuantumDevice.
        wires (Union[List[int], int]): Which qubit(s) to apply the gate.
        params (torch.Tensor, optional): Parameters (if any) of the gate.
            Default to None.
        n_wires (int, optional): Number of qubits the gate is applied to.
            Default to None.
        static (bool, optional): Whether use static mode computation.
            Default to False.
        parent_graph (tq.QuantumGraph, optional): Parent QuantumGraph of
            current operation. Default to None.
        inverse (bool, optional): Whether inverse the gate. Default to False.
        comp_method (bool, optional): Use 'bmm' or 'einsum' method to perform
        matrix vector multiplication. Default to 'bmm'.

    Returns:
        None.

    """
    name = "rxx"
    mat = mat_dict[name]
    gate_wrapper(
        name=name,
        mat=mat,
        method=comp_method,
        q_device=q_device,
        wires=wires,
        params=params,
        n_wires=n_wires,
        static=static,
        parent_graph=parent_graph,
        inverse=inverse,
    )


def ryy(
    q_device,
    wires,
    params=None,
    n_wires=None,
    static=False,
    parent_graph=None,
    inverse=False,
    comp_method="bmm",
):
    """Perform the ryy gate.

    Args:
        q_device (tq.QuantumDevice): The QuantumDevice.
        wires (Union[List[int], int]): Which qubit(s) to apply the gate.
        params (torch.Tensor, optional): Parameters (if any) of the gate.
            Default to None.
        n_wires (int, optional): Number of qubits the gate is applied to.
            Default to None.
        static (bool, optional): Whether use static mode computation.
            Default to False.
        parent_graph (tq.QuantumGraph, optional): Parent QuantumGraph of
            current operation. Default to None.
        inverse (bool, optional): Whether inverse the gate. Default to False.
        comp_method (bool, optional): Use 'bmm' or 'einsum' method to perform
        matrix vector multiplication. Default to 'bmm'.

    Returns:
        None.

    """
    name = "ryy"
    mat = mat_dict[name]
    gate_wrapper(
        name=name,
        mat=mat,
        method=comp_method,
        q_device=q_device,
        wires=wires,
        params=params,
        n_wires=n_wires,
        static=static,
        parent_graph=parent_graph,
        inverse=inverse,
    )


def rzz(
    q_device,
    wires,
    params=None,
    n_wires=None,
    static=False,
    parent_graph=None,
    inverse=False,
    comp_method="bmm",
):
    """Perform the rzz gate.

    Args:
        q_device (tq.QuantumDevice): The QuantumDevice.
        wires (Union[List[int], int]): Which qubit(s) to apply the gate.
        params (torch.Tensor, optional): Parameters (if any) of the gate.
            Default to None.
        n_wires (int, optional): Number of qubits the gate is applied to.
            Default to None.
        static (bool, optional): Whether use static mode computation.
            Default to False.
        parent_graph (tq.QuantumGraph, optional): Parent QuantumGraph of
            current operation. Default to None.
        inverse (bool, optional): Whether inverse the gate. Default to False.
        comp_method (bool, optional): Use 'bmm' or 'einsum' method to perform
        matrix vector multiplication. Default to 'bmm'.

    Returns:
        None.

    """
    name = "rzz"
    mat = mat_dict[name]
    gate_wrapper(
        name=name,
        mat=mat,
        method=comp_method,
        q_device=q_device,
        wires=wires,
        params=params,
        n_wires=n_wires,
        static=static,
        parent_graph=parent_graph,
        inverse=inverse,
    )


def rzx(
    q_device,
    wires,
    params=None,
    n_wires=None,
    static=False,
    parent_graph=None,
    inverse=False,
    comp_method="bmm",
):
    """Perform the rzx gate.

    Args:
        q_device (tq.QuantumDevice): The QuantumDevice.
        wires (Union[List[int], int]): Which qubit(s) to apply the gate.
        params (torch.Tensor, optional): Parameters (if any) of the gate.
            Default to None.
        n_wires (int, optional): Number of qubits the gate is applied to.
            Default to None.
        static (bool, optional): Whether use static mode computation.
            Default to False.
        parent_graph (tq.QuantumGraph, optional): Parent QuantumGraph of
            current operation. Default to None.
        inverse (bool, optional): Whether inverse the gate. Default to False.
        comp_method (bool, optional): Use 'bmm' or 'einsum' method to perform
        matrix vector multiplication. Default to 'bmm'.

    Returns:
        None.

    """
    name = "rzx"
    mat = mat_dict[name]
    gate_wrapper(
        name=name,
        mat=mat,
        method=comp_method,
        q_device=q_device,
        wires=wires,
        params=params,
        n_wires=n_wires,
        static=static,
        parent_graph=parent_graph,
        inverse=inverse,
    )


def swap(
    q_device,
    wires,
    params=None,
    n_wires=None,
    static=False,
    parent_graph=None,
    inverse=False,
    comp_method="bmm",
):
    """Perform the swap gate.

    Args:
        q_device (tq.QuantumDevice): The QuantumDevice.
        wires (Union[List[int], int]): Which qubit(s) to apply the gate.
        params (torch.Tensor, optional): Parameters (if any) of the gate.
            Default to None.
        n_wires (int, optional): Number of qubits the gate is applied to.
            Default to None.
        static (bool, optional): Whether use static mode computation.
            Default to False.
        parent_graph (tq.QuantumGraph, optional): Parent QuantumGraph of
            current operation. Default to None.
        inverse (bool, optional): Whether inverse the gate. Default to False.
        comp_method (bool, optional): Use 'bmm' or 'einsum' method to perform
        matrix vector multiplication. Default to 'bmm'.

    Returns:
        None.

    """
    name = "swap"
    mat = mat_dict[name]
    gate_wrapper(
        name=name,
        mat=mat,
        method=comp_method,
        q_device=q_device,
        wires=wires,
        params=params,
        n_wires=n_wires,
        static=static,
        parent_graph=parent_graph,
        inverse=inverse,
    )


def sswap(
    q_device,
    wires,
    params=None,
    n_wires=None,
    static=False,
    parent_graph=None,
    inverse=False,
    comp_method="bmm",
):
    """Perform the sswap gate.

    Args:
        q_device (tq.QuantumDevice): The QuantumDevice.
        wires (Union[List[int], int]): Which qubit(s) to apply the gate.
        params (torch.Tensor, optional): Parameters (if any) of the gate.
            Default to None.
        n_wires (int, optional): Number of qubits the gate is applied to.
            Default to None.
        static (bool, optional): Whether use static mode computation.
            Default to False.
        parent_graph (tq.QuantumGraph, optional): Parent QuantumGraph of
            current operation. Default to None.
        inverse (bool, optional): Whether inverse the gate. Default to False.
        comp_method (bool, optional): Use 'bmm' or 'einsum' method to perform
        matrix vector multiplication. Default to 'bmm'.

    Returns:
        None.

    """
    name = "sswap"
    mat = mat_dict[name]
    gate_wrapper(
        name=name,
        mat=mat,
        method=comp_method,
        q_device=q_device,
        wires=wires,
        params=params,
        n_wires=n_wires,
        static=static,
        parent_graph=parent_graph,
        inverse=inverse,
    )


def cswap(
    q_device,
    wires,
    params=None,
    n_wires=None,
    static=False,
    parent_graph=None,
    inverse=False,
    comp_method="bmm",
):
    """Perform the cswap gate.

    Args:
        q_device (tq.QuantumDevice): The QuantumDevice.
        wires (Union[List[int], int]): Which qubit(s) to apply the gate.
        params (torch.Tensor, optional): Parameters (if any) of the gate.
            Default to None.
        n_wires (int, optional): Number of qubits the gate is applied to.
            Default to None.
        static (bool, optional): Whether use static mode computation.
            Default to False.
        parent_graph (tq.QuantumGraph, optional): Parent QuantumGraph of
            current operation. Default to None.
        inverse (bool, optional): Whether inverse the gate. Default to False.
        comp_method (bool, optional): Use 'bmm' or 'einsum' method to perform
        matrix vector multiplication. Default to 'bmm'.

    Returns:
        None.

    """
    name = "cswap"
    mat = mat_dict[name]
    gate_wrapper(
        name=name,
        mat=mat,
        method=comp_method,
        q_device=q_device,
        wires=wires,
        params=params,
        n_wires=n_wires,
        static=static,
        parent_graph=parent_graph,
        inverse=inverse,
    )


def toffoli(
    q_device,
    wires,
    params=None,
    n_wires=None,
    static=False,
    parent_graph=None,
    inverse=False,
    comp_method="bmm",
):
    """Perform the toffoli gate.

    Args:
        q_device (tq.QuantumDevice): The QuantumDevice.
        wires (Union[List[int], int]): Which qubit(s) to apply the gate.
        params (torch.Tensor, optional): Parameters (if any) of the gate.
            Default to None.
        n_wires (int, optional): Number of qubits the gate is applied to.
            Default to None.
        static (bool, optional): Whether use static mode computation.
            Default to False.
        parent_graph (tq.QuantumGraph, optional): Parent QuantumGraph of
            current operation. Default to None.
        inverse (bool, optional): Whether inverse the gate. Default to False.
        comp_method (bool, optional): Use 'bmm' or 'einsum' method to perform
        matrix vector multiplication. Default to 'bmm'.

    Returns:
        None.

    """
    name = "toffoli"
    mat = mat_dict[name]
    gate_wrapper(
        name=name,
        mat=mat,
        method=comp_method,
        q_device=q_device,
        wires=wires,
        params=params,
        n_wires=n_wires,
        static=static,
        parent_graph=parent_graph,
        inverse=inverse,
    )


def phaseshift(
    q_device,
    wires,
    params=None,
    n_wires=None,
    static=False,
    parent_graph=None,
    inverse=False,
    comp_method="bmm",
):
    """Perform the phaseshift gate.

    Args:
        q_device (tq.QuantumDevice): The QuantumDevice.
        wires (Union[List[int], int]): Which qubit(s) to apply the gate.
        params (torch.Tensor, optional): Parameters (if any) of the gate.
            Default to None.
        n_wires (int, optional): Number of qubits the gate is applied to.
            Default to None.
        static (bool, optional): Whether use static mode computation.
            Default to False.
        parent_graph (tq.QuantumGraph, optional): Parent QuantumGraph of
            current operation. Default to None.
        inverse (bool, optional): Whether inverse the gate. Default to False.
        comp_method (bool, optional): Use 'bmm' or 'einsum' method to perform
        matrix vector multiplication. Default to 'bmm'.

    Returns:
        None.

    """
    name = "phaseshift"
    mat = mat_dict[name]
    gate_wrapper(
        name=name,
        mat=mat,
        method=comp_method,
        q_device=q_device,
        wires=wires,
        params=params,
        n_wires=n_wires,
        static=static,
        parent_graph=parent_graph,
        inverse=inverse,
    )


def rot(
    q_device,
    wires,
    params=None,
    n_wires=None,
    static=False,
    parent_graph=None,
    inverse=False,
    comp_method="bmm",
):
    """Perform the rot gate.

    Args:
        q_device (tq.QuantumDevice): The QuantumDevice.
        wires (Union[List[int], int]): Which qubit(s) to apply the gate.
        params (torch.Tensor, optional): Parameters (if any) of the gate.
            Default to None.
        n_wires (int, optional): Number of qubits the gate is applied to.
            Default to None.
        static (bool, optional): Whether use static mode computation.
            Default to False.
        parent_graph (tq.QuantumGraph, optional): Parent QuantumGraph of
            current operation. Default to None.
        inverse (bool, optional): Whether inverse the gate. Default to False.
        comp_method (bool, optional): Use 'bmm' or 'einsum' method to perform
        matrix vector multiplication. Default to 'bmm'.

    Returns:
        None.

    """
    name = "rot"
    mat = mat_dict[name]
    gate_wrapper(
        name=name,
        mat=mat,
        method=comp_method,
        q_device=q_device,
        wires=wires,
        params=params,
        n_wires=n_wires,
        static=static,
        parent_graph=parent_graph,
        inverse=inverse,
    )


def xxminyy(
    q_device,
    wires,
    params=None,
    n_wires=None,
    static=False,
    parent_graph=None,
    inverse=False,
    comp_method="bmm",
):
    """Perform the XXminusYY gate.

    Args:
        q_device (tq.QuantumDevice): The QuantumDevice.
        wires (Union[List[int], int]): Which qubit(s) to apply the gate.
        params (torch.Tensor, optional): Parameters (if any) of the gate.
            Default to None.
        n_wires (int, optional): Number of qubits the gate is applied to.
            Default to None.
        static (bool, optional): Whether use static mode computation.
            Default to False.
        parent_graph (tq.QuantumGraph, optional): Parent QuantumGraph of
            current operation. Default to None.
        inverse (bool, optional): Whether inverse the gate. Default to False.
        comp_method (bool, optional): Use 'bmm' or 'einsum' method to perform
        matrix vector multiplication. Default to 'bmm'.

    Returns:
        None.

    """
    name = "xxminyy"
    mat = mat_dict[name]
    gate_wrapper(
        name=name,
        mat=mat,
        method=comp_method,
        q_device=q_device,
        wires=wires,
        params=params,
        n_wires=n_wires,
        static=static,
        parent_graph=parent_graph,
        inverse=inverse,
    )


def xxplusyy(
    q_device,
    wires,
    params=None,
    n_wires=None,
    static=False,
    parent_graph=None,
    inverse=False,
    comp_method="bmm",
):
    """Perform the XXPlusYY gate.

    Args:
        q_device (tq.QuantumDevice): The QuantumDevice.
        wires (Union[List[int], int]): Which qubit(s) to apply the gate.
        params (torch.Tensor, optional): Parameters (if any) of the gate.
            Default to None.
        n_wires (int, optional): Number of qubits the gate is applied to.
            Default to None.
        static (bool, optional): Whether use static mode computation.
            Default to False.
        parent_graph (tq.QuantumGraph, optional): Parent QuantumGraph of
            current operation. Default to None.
        inverse (bool, optional): Whether inverse the gate. Default to False.
        comp_method (bool, optional): Use 'bmm' or 'einsum' method to perform
        matrix vector multiplication. Default to 'bmm'.

    Returns:
        None.

    """
    name = "xxplusyy"
    mat = mat_dict[name]
    gate_wrapper(
        name=name,
        mat=mat,
        method=comp_method,
        q_device=q_device,
        wires=wires,
        params=params,
        n_wires=n_wires,
        static=static,
        parent_graph=parent_graph,
        inverse=inverse,
    )


def multirz(
    q_device,
    wires,
    params=None,
    n_wires=None,
    static=False,
    parent_graph=None,
    inverse=False,
    comp_method="bmm",
):
    """Perform the multi qubit RZ gate.

    Args:
        q_device (tq.QuantumDevice): The QuantumDevice.
        wires (Union[List[int], int]): Which qubit(s) to apply the gate.
        params (torch.Tensor, optional): Parameters (if any) of the gate.
            Default to None.
        n_wires (int, optional): Number of qubits the gate is applied to.
            Default to None.
        static (bool, optional): Whether use static mode computation.
            Default to False.
        parent_graph (tq.QuantumGraph, optional): Parent QuantumGraph of
            current operation. Default to None.
        inverse (bool, optional): Whether inverse the gate. Default to False.
        comp_method (bool, optional): Use 'bmm' or 'einsum' method to perform
        matrix vector multiplication. Default to 'bmm'.

    Returns:
        None.

    """
    name = "multirz"
    mat = mat_dict[name]
    gate_wrapper(
        name=name,
        mat=mat,
        method=comp_method,
        q_device=q_device,
        wires=wires,
        params=params,
        n_wires=n_wires,
        static=static,
        parent_graph=parent_graph,
        inverse=inverse,
    )


def crx(
    q_device,
    wires,
    params=None,
    n_wires=None,
    static=False,
    parent_graph=None,
    inverse=False,
    comp_method="bmm",
):
    """Perform the crx gate.

    Args:
        q_device (tq.QuantumDevice): The QuantumDevice.
        wires (Union[List[int], int]): Which qubit(s) to apply the gate.
        params (torch.Tensor, optional): Parameters (if any) of the gate.
            Default to None.
        n_wires (int, optional): Number of qubits the gate is applied to.
            Default to None.
        static (bool, optional): Whether use static mode computation.
            Default to False.
        parent_graph (tq.QuantumGraph, optional): Parent QuantumGraph of
            current operation. Default to None.
        inverse (bool, optional): Whether inverse the gate. Default to False.
        comp_method (bool, optional): Use 'bmm' or 'einsum' method to perform
        matrix vector multiplication. Default to 'bmm'.

    Returns:
        None.

    """
    name = "crx"
    mat = mat_dict[name]
    gate_wrapper(
        name=name,
        mat=mat,
        method=comp_method,
        q_device=q_device,
        wires=wires,
        params=params,
        n_wires=n_wires,
        static=static,
        parent_graph=parent_graph,
        inverse=inverse,
    )


def cry(
    q_device,
    wires,
    params=None,
    n_wires=None,
    static=False,
    parent_graph=None,
    inverse=False,
    comp_method="bmm",
):
    """Perform the cry gate.

    Args:
        q_device (tq.QuantumDevice): The QuantumDevice.
        wires (Union[List[int], int]): Which qubit(s) to apply the gate.
        params (torch.Tensor, optional): Parameters (if any) of the gate.
            Default to None.
        n_wires (int, optional): Number of qubits the gate is applied to.
            Default to None.
        static (bool, optional): Whether use static mode computation.
            Default to False.
        parent_graph (tq.QuantumGraph, optional): Parent QuantumGraph of
            current operation. Default to None.
        inverse (bool, optional): Whether inverse the gate. Default to False.
        comp_method (bool, optional): Use 'bmm' or 'einsum' method to perform
        matrix vector multiplication. Default to 'bmm'.

    Returns:
        None.

    """
    name = "cry"
    mat = mat_dict[name]
    gate_wrapper(
        name=name,
        mat=mat,
        method=comp_method,
        q_device=q_device,
        wires=wires,
        params=params,
        n_wires=n_wires,
        static=static,
        parent_graph=parent_graph,
        inverse=inverse,
    )


def crz(
    q_device,
    wires,
    params=None,
    n_wires=None,
    static=False,
    parent_graph=None,
    inverse=False,
    comp_method="bmm",
):
    """Perform the crz gate.

    Args:
        q_device (tq.QuantumDevice): The QuantumDevice.
        wires (Union[List[int], int]): Which qubit(s) to apply the gate.
        params (torch.Tensor, optional): Parameters (if any) of the gate.
            Default to None.
        n_wires (int, optional): Number of qubits the gate is applied to.
            Default to None.
        static (bool, optional): Whether use static mode computation.
            Default to False.
        parent_graph (tq.QuantumGraph, optional): Parent QuantumGraph of
            current operation. Default to None.
        inverse (bool, optional): Whether inverse the gate. Default to False.
        comp_method (bool, optional): Use 'bmm' or 'einsum' method to perform
        matrix vector multiplication. Default to 'bmm'.

    Returns:
        None.

    """
    name = "crz"
    mat = mat_dict[name]
    gate_wrapper(
        name=name,
        mat=mat,
        method=comp_method,
        q_device=q_device,
        wires=wires,
        params=params,
        n_wires=n_wires,
        static=static,
        parent_graph=parent_graph,
        inverse=inverse,
    )


def crot(
    q_device,
    wires,
    params=None,
    n_wires=None,
    static=False,
    parent_graph=None,
    inverse=False,
    comp_method="bmm",
):
    """Perform the crot gate.

    Args:
        q_device (tq.QuantumDevice): The QuantumDevice.
        wires (Union[List[int], int]): Which qubit(s) to apply the gate.
        params (torch.Tensor, optional): Parameters (if any) of the gate.
            Default to None.
        n_wires (int, optional): Number of qubits the gate is applied to.
            Default to None.
        static (bool, optional): Whether use static mode computation.
            Default to False.
        parent_graph (tq.QuantumGraph, optional): Parent QuantumGraph of
            current operation. Default to None.
        inverse (bool, optional): Whether inverse the gate. Default to False.
        comp_method (bool, optional): Use 'bmm' or 'einsum' method to perform
        matrix vector multiplication. Default to 'bmm'.

    Returns:
        None.

    """
    name = "crot"
    mat = mat_dict[name]
    gate_wrapper(
        name=name,
        mat=mat,
        method=comp_method,
        q_device=q_device,
        wires=wires,
        params=params,
        n_wires=n_wires,
        static=static,
        parent_graph=parent_graph,
        inverse=inverse,
    )


def u1(
    q_device,
    wires,
    params=None,
    n_wires=None,
    static=False,
    parent_graph=None,
    inverse=False,
    comp_method="bmm",
):
    """Perform the u1 gate.

    Args:
        q_device (tq.QuantumDevice): The QuantumDevice.
        wires (Union[List[int], int]): Which qubit(s) to apply the gate.
        params (torch.Tensor, optional): Parameters (if any) of the gate.
            Default to None.
        n_wires (int, optional): Number of qubits the gate is applied to.
            Default to None.
        static (bool, optional): Whether use static mode computation.
            Default to False.
        parent_graph (tq.QuantumGraph, optional): Parent QuantumGraph of
            current operation. Default to None.
        inverse (bool, optional): Whether inverse the gate. Default to False.
        comp_method (bool, optional): Use 'bmm' or 'einsum' method to perform
        matrix vector multiplication. Default to 'bmm'.

    Returns:
        None.

    """
    name = "u1"
    mat = mat_dict[name]
    gate_wrapper(
        name=name,
        mat=mat,
        method=comp_method,
        q_device=q_device,
        wires=wires,
        params=params,
        n_wires=n_wires,
        static=static,
        parent_graph=parent_graph,
        inverse=inverse,
    )


def u2(
    q_device,
    wires,
    params=None,
    n_wires=None,
    static=False,
    parent_graph=None,
    inverse=False,
    comp_method="bmm",
):
    """Perform the u2 gate.

    Args:
        q_device (tq.QuantumDevice): The QuantumDevice.
        wires (Union[List[int], int]): Which qubit(s) to apply the gate.
        params (torch.Tensor, optional): Parameters (if any) of the gate.
            Default to None.
        n_wires (int, optional): Number of qubits the gate is applied to.
            Default to None.
        static (bool, optional): Whether use static mode computation.
            Default to False.
        parent_graph (tq.QuantumGraph, optional): Parent QuantumGraph of
            current operation. Default to None.
        inverse (bool, optional): Whether inverse the gate. Default to False.
        comp_method (bool, optional): Use 'bmm' or 'einsum' method to perform
        matrix vector multiplication. Default to 'bmm'.

    Returns:
        None.

    """
    name = "u2"
    mat = mat_dict[name]
    gate_wrapper(
        name=name,
        mat=mat,
        method=comp_method,
        q_device=q_device,
        wires=wires,
        params=params,
        n_wires=n_wires,
        static=static,
        parent_graph=parent_graph,
        inverse=inverse,
    )


def u3(
    q_device,
    wires,
    params=None,
    n_wires=None,
    static=False,
    parent_graph=None,
    inverse=False,
    comp_method="bmm",
):
    """Perform the u3 gate.

    Args:
        q_device (tq.QuantumDevice): The QuantumDevice.
        wires (Union[List[int], int]): Which qubit(s) to apply the gate.
        params (torch.Tensor, optional): Parameters (if any) of the gate.
            Default to None.
        n_wires (int, optional): Number of qubits the gate is applied to.
            Default to None.
        static (bool, optional): Whether use static mode computation.
            Default to False.
        parent_graph (tq.QuantumGraph, optional): Parent QuantumGraph of
            current operation. Default to None.
        inverse (bool, optional): Whether inverse the gate. Default to False.
        comp_method (bool, optional): Use 'bmm' or 'einsum' method to perform
        matrix vector multiplication. Default to 'bmm'.

    Returns:
        None.

    """
    name = "u3"
    mat = mat_dict[name]
    gate_wrapper(
        name=name,
        mat=mat,
        method=comp_method,
        q_device=q_device,
        wires=wires,
        params=params,
        n_wires=n_wires,
        static=static,
        parent_graph=parent_graph,
        inverse=inverse,
    )


def cu(
    q_device,
    wires,
    params=None,
    n_wires=None,
    static=False,
    parent_graph=None,
    inverse=False,
    comp_method="bmm",
):
    """Perform the cu gate.
    Args:
        q_device (tq.QuantumDevice): The QuantumDevice.
        wires (Union[List[int], int]): Which qubit(s) to apply the gate.
        params (torch.Tensor, optional): Parameters (if any) of the gate.
            Default to None.
        n_wires (int, optional): Number of qubits the gate is applied to.
            Default to None.
        static (bool, optional): Whether use static mode computation.
            Default to False.
        parent_graph (tq.QuantumGraph, optional): Parent QuantumGraph of
            current operation. Default to None.
        inverse (bool, optional): Whether inverse the gate. Default to False.
        comp_method (bool, optional): Use 'bmm' or 'einsum' method to perform
        matrix vector multiplication. Default to 'bmm'.
    Returns:
        None.
    """
    name = "cu"
    mat = mat_dict[name]
    gate_wrapper(
        name=name,
        mat=mat,
        method=comp_method,
        q_device=q_device,
        wires=wires,
        params=params,
        n_wires=n_wires,
        static=static,
        parent_graph=parent_graph,
        inverse=inverse,
    )


def cu1(
    q_device,
    wires,
    params=None,
    n_wires=None,
    static=False,
    parent_graph=None,
    inverse=False,
    comp_method="bmm",
):
    """Perform the cu1 gate.

    Args:
        q_device (tq.QuantumDevice): The QuantumDevice.
        wires (Union[List[int], int]): Which qubit(s) to apply the gate.
        params (torch.Tensor, optional): Parameters (if any) of the gate.
            Default to None.
        n_wires (int, optional): Number of qubits the gate is applied to.
            Default to None.
        static (bool, optional): Whether use static mode computation.
            Default to False.
        parent_graph (tq.QuantumGraph, optional): Parent QuantumGraph of
            current operation. Default to None.
        inverse (bool, optional): Whether inverse the gate. Default to False.
        comp_method (bool, optional): Use 'bmm' or 'einsum' method to perform
        matrix vector multiplication. Default to 'bmm'.

    Returns:
        None.

    """
    name = "cu1"
    mat = mat_dict[name]
    gate_wrapper(
        name=name,
        mat=mat,
        method=comp_method,
        q_device=q_device,
        wires=wires,
        params=params,
        n_wires=n_wires,
        static=static,
        parent_graph=parent_graph,
        inverse=inverse,
    )


def cu2(
    q_device,
    wires,
    params=None,
    n_wires=None,
    static=False,
    parent_graph=None,
    inverse=False,
    comp_method="bmm",
):
    """Perform the cu2 gate.

    Args:
        q_device (tq.QuantumDevice): The QuantumDevice.
        wires (Union[List[int], int]): Which qubit(s) to apply the gate.
        params (torch.Tensor, optional): Parameters (if any) of the gate.
            Default to None.
        n_wires (int, optional): Number of qubits the gate is applied to.
            Default to None.
        static (bool, optional): Whether use static mode computation.
            Default to False.
        parent_graph (tq.QuantumGraph, optional): Parent QuantumGraph of
            current operation. Default to None.
        inverse (bool, optional): Whether inverse the gate. Default to False.
        comp_method (bool, optional): Use 'bmm' or 'einsum' method to perform
        matrix vector multiplication. Default to 'bmm'.

    Returns:
        None.

    """
    name = "cu2"
    mat = mat_dict[name]
    gate_wrapper(
        name=name,
        mat=mat,
        method=comp_method,
        q_device=q_device,
        wires=wires,
        params=params,
        n_wires=n_wires,
        static=static,
        parent_graph=parent_graph,
        inverse=inverse,
    )


def cu3(
    q_device,
    wires,
    params=None,
    n_wires=None,
    static=False,
    parent_graph=None,
    inverse=False,
    comp_method="bmm",
):
    """Perform the cu3 gate.

    Args:
        q_device (tq.QuantumDevice): The QuantumDevice.
        wires (Union[List[int], int]): Which qubit(s) to apply the gate.
        params (torch.Tensor, optional): Parameters (if any) of the gate.
            Default to None.
        n_wires (int, optional): Number of qubits the gate is applied to.
            Default to None.
        static (bool, optional): Whether use static mode computation.
            Default to False.
        parent_graph (tq.QuantumGraph, optional): Parent QuantumGraph of
            current operation. Default to None.
        inverse (bool, optional): Whether inverse the gate. Default to False.
        comp_method (bool, optional): Use 'bmm' or 'einsum' method to perform
        matrix vector multiplication. Default to 'bmm'.

    Returns:
        None.

    """
    name = "cu3"
    mat = mat_dict[name]
    gate_wrapper(
        name=name,
        mat=mat,
        method=comp_method,
        q_device=q_device,
        wires=wires,
        params=params,
        n_wires=n_wires,
        static=static,
        parent_graph=parent_graph,
        inverse=inverse,
    )


def su4(
    q_device,
    wires,
    params=None,
    n_wires=None,
    static=False,
    parent_graph=None,
    inverse=False,
    comp_method="bmm",
):
    """Perform the su4 gate.

    Args:
        q_device (tq.QuantumDevice): The QuantumDevice.
        wires (Union[List[int], int]): Which qubit(s) to apply the gate.
        params (torch.Tensor, optional): Parameters (if any) of the gate.
            Default to None.
        n_wires (int, optional): Number of qubits the gate is applied to.
            Default to None.
        static (bool, optional): Whether use static mode computation.
            Default to False.
        parent_graph (tq.QuantumGraph, optional): Parent QuantumGraph of
            current operation. Default to None.
        inverse (bool, optional): Whether inverse the gate. Default to False.
        comp_method (bool, optional): Use 'bmm' or 'einsum' method to perform
        matrix vector multiplication. Default to 'bmm'.

    Returns:
        None.

    """
    name = "su4"
    mat = mat_dict[name]
    gate_wrapper(
        name=name,
        mat=mat,
        method=comp_method,
        q_device=q_device,
        wires=wires,
        params=params,
        n_wires=n_wires,
        static=static,
        parent_graph=parent_graph,
        inverse=inverse,
    )


def qubitunitary(
    q_device,
    wires,
    params=None,
    n_wires=None,
    static=False,
    parent_graph=None,
    inverse=False,
    comp_method="bmm",
):
    """Perform the qubitunitary gate.

    Args:
        q_device (tq.QuantumDevice): The QuantumDevice.
        wires (Union[List[int], int]): Which qubit(s) to apply the gate.
        params (torch.Tensor, optional): Parameters (if any) of the gate.
            Default to None.
        n_wires (int, optional): Number of qubits the gate is applied to.
            Default to None.
        static (bool, optional): Whether use static mode computation.
            Default to False.
        parent_graph (tq.QuantumGraph, optional): Parent QuantumGraph of
            current operation. Default to None.
        inverse (bool, optional): Whether inverse the gate. Default to False.
        comp_method (bool, optional): Use 'bmm' or 'einsum' method to perform
        matrix vector multiplication. Default to 'bmm'.

    Returns:
        None.

    """
    name = "qubitunitary"
    mat = mat_dict[name]
    gate_wrapper(
        name=name,
        mat=mat,
        method=comp_method,
        q_device=q_device,
        wires=wires,
        params=params,
        n_wires=n_wires,
        static=static,
        parent_graph=parent_graph,
        inverse=inverse,
    )


def qubitunitaryfast(
    q_device,
    wires,
    params=None,
    n_wires=None,
    static=False,
    parent_graph=None,
    inverse=False,
    comp_method="bmm",
):
    """Perform the qubitunitaryfast gate.

    Args:
        q_device (tq.QuantumDevice): The QuantumDevice.
        wires (Union[List[int], int]): Which qubit(s) to apply the gate.
        params (torch.Tensor, optional): Parameters (if any) of the gate.
            Default to None.
        n_wires (int, optional): Number of qubits the gate is applied to.
            Default to None.
        static (bool, optional): Whether use static mode computation.
            Default to False.
        parent_graph (tq.QuantumGraph, optional): Parent QuantumGraph of
            current operation. Default to None.
        inverse (bool, optional): Whether inverse the gate. Default to False.
        comp_method (bool, optional): Use 'bmm' or 'einsum' method to perform
        matrix vector multiplication. Default to 'bmm'.

    Returns:
        None.

    """
    name = "qubitunitaryfast"
    mat = mat_dict[name]
    gate_wrapper(
        name=name,
        mat=mat,
        method=comp_method,
        q_device=q_device,
        wires=wires,
        params=params,
        n_wires=n_wires,
        static=static,
        parent_graph=parent_graph,
        inverse=inverse,
    )


def qubitunitarystrict(
    q_device,
    wires,
    params=None,
    n_wires=None,
    static=False,
    parent_graph=None,
    inverse=False,
    comp_method="bmm",
):
    """Perform the qubitunitarystrict = gate.

    Args:
        q_device (tq.QuantumDevice): The QuantumDevice.
        wires (Union[List[int], int]): Which qubit(s) to apply the gate.
        params (torch.Tensor, optional): Parameters (if any) of the gate.
            Default to None.
        n_wires (int, optional): Number of qubits the gate is applied to.
            Default to None.
        static (bool, optional): Whether use static mode computation.
            Default to False.
        parent_graph (tq.QuantumGraph, optional): Parent QuantumGraph of
            current operation. Default to None.
        inverse (bool, optional): Whether inverse the gate. Default to False.
        comp_method (bool, optional): Use 'bmm' or 'einsum' method to perform
        matrix vector multiplication. Default to 'bmm'.

    Returns:
        None.

    """
    name = "qubitunitarystrict"
    mat = mat_dict[name]
    gate_wrapper(
        name=name,
        mat=mat,
        method=comp_method,
        q_device=q_device,
        wires=wires,
        params=params,
        n_wires=n_wires,
        static=static,
        parent_graph=parent_graph,
        inverse=inverse,
    )


def c3x(
    q_device,
    wires,
    params=None,
    n_wires=None,
    static=False,
    parent_graph=None,
    inverse=False,
    comp_method="bmm",
):
    """Perform the c3x gate.

    Args:
        q_device (tq.QuantumDevice): The QuantumDevice.
        wires (Union[List[int], int]): Which qubit(s) to apply the gate.
        params (torch.Tensor, optional): Parameters (if any) of the gate.
            Default to None.
        n_wires (int, optional): Number of qubits the gate is applied to.
            Default to None.
        static (bool, optional): Whether use static mode computation.
            Default to False.
        parent_graph (tq.QuantumGraph, optional): Parent QuantumGraph of
            current operation. Default to None.
        inverse (bool, optional): Whether inverse the gate. Default to False.
        comp_method (bool, optional): Use 'bmm' or 'einsum' method to perform
        matrix vector multiplication. Default to 'bmm'.

    Returns:
        None.

    """
    name = "c3x"
    mat = mat_dict[name]
    gate_wrapper(
        name=name,
        mat=mat,
        method=comp_method,
        q_device=q_device,
        wires=wires,
        params=params,
        n_wires=n_wires,
        static=static,
        parent_graph=parent_graph,
        inverse=inverse,
    )


def multicnot(
    q_device,
    wires,
    params=None,
    n_wires=None,
    static=False,
    parent_graph=None,
    inverse=False,
    comp_method="bmm",
):
    """Perform the multi qubit cnot gate.

    Args:
        q_device (tq.QuantumDevice): The QuantumDevice.
        wires (Union[List[int], int]): Which qubit(s) to apply the gate.
        params (torch.Tensor, optional): Parameters (if any) of the gate.
            Default to None.
        n_wires (int, optional): Number of qubits the gate is applied to.
            Default to None.
        static (bool, optional): Whether use static mode computation.
            Default to False.
        parent_graph (tq.QuantumGraph, optional): Parent QuantumGraph of
            current operation. Default to None.
        inverse (bool, optional): Whether inverse the gate. Default to False.
        comp_method (bool, optional): Use 'bmm' or 'einsum' method to perform
        matrix vector multiplication. Default to 'bmm'.

    Returns:
        None.

    """
    name = "multicnot"
    mat = mat_dict[name]
    gate_wrapper(
        name=name,
        mat=mat,
        method=comp_method,
        q_device=q_device,
        wires=wires,
        params=params,
        n_wires=n_wires,
        static=static,
        parent_graph=parent_graph,
        inverse=inverse,
    )


def multixcnot(
    q_device,
    wires,
    params=None,
    n_wires=None,
    static=False,
    parent_graph=None,
    inverse=False,
    comp_method="bmm",
):
    """Perform the multi qubit xcnot gate.

    Args:
        q_device (tq.QuantumDevice): The QuantumDevice.
        wires (Union[List[int], int]): Which qubit(s) to apply the gate.
        params (torch.Tensor, optional): Parameters (if any) of the gate.
            Default to None.
        n_wires (int, optional): Number of qubits the gate is applied to.
            Default to None.
        static (bool, optional): Whether use static mode computation.
            Default to False.
        parent_graph (tq.QuantumGraph, optional): Parent QuantumGraph of
            current operation. Default to None.
        inverse (bool, optional): Whether inverse the gate. Default to False.
        comp_method (bool, optional): Use 'bmm' or 'einsum' method to perform
        matrix vector multiplication. Default to 'bmm'.

    Returns:
        None.

    """
    name = "multixcnot"
    mat = mat_dict[name]
    gate_wrapper(
        name=name,
        mat=mat,
        method=comp_method,
        q_device=q_device,
        wires=wires,
        params=params,
        n_wires=n_wires,
        static=static,
        parent_graph=parent_graph,
        inverse=inverse,
    )


def singleexcitation(
    q_device,
    wires,
    params=None,
    n_wires=None,
    static=False,
    parent_graph=None,
    inverse=False,
    comp_method="bmm",
):
    """Perform the single excitation gate.

    Args:
        q_device (tq.QuantumDevice): The QuantumDevice.
        wires (Union[List[int], int]): Which qubit(s) to apply the gate.
        params (torch.Tensor, optional): Parameters (if any) of the gate.
            Default to None.
        n_wires (int, optional): Number of qubits the gate is applied to.
            Default to None.
        static (bool, optional): Whether use static mode computation.
            Default to False.
        parent_graph (tq.QuantumGraph, optional): Parent QuantumGraph of
            current operation. Default to None.
        inverse (bool, optional): Whether inverse the gate. Default to False.
        comp_method (bool, optional): Use 'bmm' or 'einsum' method to perform
        matrix vector multiplication. Default to 'bmm'.

    Returns:
        None.

    """
    name = "singleexcitation"
    mat = mat_dict[name]
    gate_wrapper(
        name=name,
        mat=mat,
        method=comp_method,
        q_device=q_device,
        wires=wires,
        params=params,
        n_wires=n_wires,
        static=static,
        parent_graph=parent_graph,
        inverse=inverse,
    )


def ecr(
    q_device,
    wires,
    params=None,
    n_wires=None,
    static=False,
    parent_graph=None,
    inverse=False,
    comp_method="bmm",
):
    """Perform the echoed cross-resonance gate.
    https://qiskit.org/documentation/stubs/qiskit.circuit.library.ECRGate.html

    Args:
        q_device (tq.QuantumDevice): The QuantumDevice.
        wires (Union[List[int], int]): Which qubit(s) to apply the gate.
        params (torch.Tensor, optional): Parameters (if any) of the gate.
            Default to None.
        n_wires (int, optional): Number of qubits the gate is applied to.
            Default to None.
        static (bool, optional): Whether use static mode computation.
            Default to False.
        parent_graph (tq.QuantumGraph, optional): Parent QuantumGraph of
            current operation. Default to None.
        inverse (bool, optional): Whether inverse the gate. Default to False.
        comp_method (bool, optional): Use 'bmm' or 'einsum' method to perform
        matrix vector multiplication. Default to 'bmm'.

    Returns:
        None.

    """
    name = "ecr"
    mat = mat_dict[name]
    gate_wrapper(
        name=name,
        mat=mat,
        method=comp_method,
        q_device=q_device,
        wires=wires,
        params=params,
        n_wires=n_wires,
        static=static,
        parent_graph=parent_graph,
        inverse=inverse,
    )


def qft(
    q_device,
    wires,
    params=None,
    n_wires=None,
    static=False,
    parent_graph=None,
    inverse=False,
    comp_method="bmm",
):
    name = "qft"
    if n_wires == None:
        wires = [wires] if isinstance(wires, int) else wires
        n_wires = len(wires)

    mat = mat_dict[name]
    # mat = qft_matrix(n_wires)
    gate_wrapper(
        name=name,
        mat=mat,
        method=comp_method,
        q_device=q_device,
        wires=wires,
        params=params,
        n_wires=n_wires,
        static=static,
        parent_graph=parent_graph,
        inverse=inverse,
    )


def sdg(
    q_device: QuantumDevice,
    wires: Union[List[int], int],
    params: torch.Tensor = None,
    n_wires: int = None,
    static: bool = False,
    parent_graph=None,
    inverse: bool = False,
    comp_method: str = "bmm",
):
    """Perform the sdg gate.

    Args:
        q_device (tq.QuantumDevice): The QuantumDevice.
        wires (Union[List[int], int]): Which qubit(s) to apply the gate.
        params (torch.Tensor, optional): Parameters (if any) of the gate.
            Default to None.
        n_wires (int, optional): Number of qubits the gate is applied to.
            Default to None.
        static (bool, optional): Whether use static mode computation.
            Default to False.
        parent_graph (tq.QuantumGraph, optional): Parent QuantumGraph of
            current operation. Default to None.
        inverse (bool, optional): Whether inverse the gate. Default to False.
        comp_method (bool, optional): Use 'bmm' or 'einsum' method to perform
        matrix vector multiplication. Default to 'bmm'.

    Returns:
        None.

    """
    name = "sdg"
    mat = mat_dict[name]
    gate_wrapper(
        name=name,
        mat=mat,
        method=comp_method,
        q_device=q_device,
        wires=wires,
        params=params,
        n_wires=n_wires,
        static=static,
        parent_graph=parent_graph,
        inverse=inverse,
    )


def tdg(
    q_device: QuantumDevice,
    wires: Union[List[int], int],
    params: torch.Tensor = None,
    n_wires: int = None,
    static: bool = False,
    parent_graph=None,
    inverse: bool = False,
    comp_method: str = "bmm",
):
    """Perform the tdg gate.

    Args:
        q_device (tq.QuantumDevice): The QuantumDevice.
        wires (Union[List[int], int]): Which qubit(s) to apply the gate.
        params (torch.Tensor, optional): Parameters (if any) of the gate.
            Default to None.
        n_wires (int, optional): Number of qubits the gate is applied to.
            Default to None.
        static (bool, optional): Whether use static mode computation.
            Default to False.
        parent_graph (tq.QuantumGraph, optional): Parent QuantumGraph of
            current operation. Default to None.
        inverse (bool, optional): Whether inverse the gate. Default to False.
        comp_method (bool, optional): Use 'bmm' or 'einsum' method to perform
        matrix vector multiplication. Default to 'bmm'.

    Returns:
        None.

    """
    name = "tdg"
    mat = mat_dict[name]
    gate_wrapper(
        name=name,
        mat=mat,
        method=comp_method,
        q_device=q_device,
        wires=wires,
        params=params,
        n_wires=n_wires,
        static=static,
        parent_graph=parent_graph,
        inverse=inverse,
    )


def sxdg(
    q_device: QuantumDevice,
    wires: Union[List[int], int],
    params: torch.Tensor = None,
    n_wires: int = None,
    static: bool = False,
    parent_graph=None,
    inverse: bool = False,
    comp_method: str = "bmm",
):
    """Perform the sxdg gate.

    Args:
        q_device (tq.QuantumDevice): The QuantumDevice.
        wires (Union[List[int], int]): Which qubit(s) to apply the gate.
        params (torch.Tensor, optional): Parameters (if any) of the gate.
            Default to None.
        n_wires (int, optional): Number of qubits the gate is applied to.
            Default to None.
        static (bool, optional): Whether use static mode computation.
            Default to False.
        parent_graph (tq.QuantumGraph, optional): Parent QuantumGraph of
            current operation. Default to None.
        inverse (bool, optional): Whether inverse the gate. Default to False.
        comp_method (bool, optional): Use 'bmm' or 'einsum' method to perform
        matrix vector multiplication. Default to 'bmm'.

    Returns:
        None.

    """
    name = "sxdg"
    mat = mat_dict[name]
    gate_wrapper(
        name=name,
        mat=mat,
        method=comp_method,
        q_device=q_device,
        wires=wires,
        params=params,
        n_wires=n_wires,
        static=static,
        parent_graph=parent_graph,
        inverse=inverse,
    )


def chadamard(
    q_device,
    wires,
    params=None,
    n_wires=None,
    static=False,
    parent_graph=None,
    inverse=False,
    comp_method="bmm",
):
    """Perform the chadamard gate.

    Args:
        q_device (tq.QuantumDevice): The QuantumDevice.
        wires (Union[List[int], int]): Which qubit(s) to apply the gate.
        params (torch.Tensor, optional): Parameters (if any) of the gate.
            Default to None.
        n_wires (int, optional): Number of qubits the gate is applied to.
            Default to None.
        static (bool, optional): Whether use static mode computation.
            Default to False.
        parent_graph (tq.QuantumGraph, optional): Parent QuantumGraph of
            current operation. Default to None.
        inverse (bool, optional): Whether inverse the gate. Default to False.
        comp_method (bool, optional): Use 'bmm' or 'einsum' method to perform
        matrix vector multiplication. Default to 'bmm'.

    Returns:
        None.

    """

    name = "chadamard"

    mat = mat_dict[name]
    gate_wrapper(
        name=name,
        mat=mat,
        method=comp_method,
        q_device=q_device,
        wires=wires,
        params=params,
        n_wires=n_wires,
        static=static,
        parent_graph=parent_graph,
        inverse=inverse,
    )


def ccz(
    q_device,
    wires,
    params=None,
    n_wires=None,
    static=False,
    parent_graph=None,
    inverse=False,
    comp_method="bmm",
):
    """Perform the ccz gate.

    Args:
        q_device (tq.QuantumDevice): The QuantumDevice.
        wires (Union[List[int], int]): Which qubit(s) to apply the gate.
        params (torch.Tensor, optional): Parameters (if any) of the gate.
            Default to None.
        n_wires (int, optional): Number of qubits the gate is applied to.
            Default to None.
        static (bool, optional): Whether use static mode computation.
            Default to False.
        parent_graph (tq.QuantumGraph, optional): Parent QuantumGraph of
            current operation. Default to None.
        inverse (bool, optional): Whether inverse the gate. Default to False.
        comp_method (bool, optional): Use 'bmm' or 'einsum' method to perform
        matrix vector multiplication. Default to 'bmm'.

    Returns:
        None.

    """
    name = "ccz"
    mat = mat_dict[name]
    gate_wrapper(
        name=name,
        mat=mat,
        method=comp_method,
        q_device=q_device,
        wires=wires,
        params=params,
        n_wires=n_wires,
        static=static,
        parent_graph=parent_graph,
        inverse=inverse,
    )


def iswap(
    q_device,
    wires,
    params=None,
    n_wires=None,
    static=False,
    parent_graph=None,
    inverse=False,
    comp_method="bmm",
):
    """Perform the iswap gate.

    Args:
        q_device (tq.QuantumDevice): The QuantumDevice.
        wires (Union[List[int], int]): Which qubit(s) to apply the gate.
        params (torch.Tensor, optional): Parameters (if any) of the gate.
            Default to None.
        n_wires (int, optional): Number of qubits the gate is applied to.
            Default to None.
        static (bool, optional): Whether use static mode computation.
            Default to False.
        parent_graph (tq.QuantumGraph, optional): Parent QuantumGraph of
            current operation. Default to None.
        inverse (bool, optional): Whether inverse the gate. Default to False.
        comp_method (bool, optional): Use 'bmm' or 'einsum' method to perform
        matrix vector multiplication. Default to 'bmm'.

    Returns:
        None.

    """
    name = "iswap"
    mat = mat_dict[name]
    gate_wrapper(
        name=name,
        mat=mat,
        method=comp_method,
        q_device=q_device,
        wires=wires,
        params=params,
        n_wires=n_wires,
        static=static,
        parent_graph=parent_graph,
        inverse=inverse,
    )


def cs(
    q_device,
    wires,
    params=None,
    n_wires=None,
    static=False,
    parent_graph=None,
    inverse=False,
    comp_method="bmm",
):
    """Perform the cs gate.

    Args:
        q_device (tq.QuantumDevice): The QuantumDevice.
        wires (Union[List[int], int]): Which qubit(s) to apply the gate.
        params (torch.Tensor, optional): Parameters (if any) of the gate.
            Default to None.
        n_wires (int, optional): Number of qubits the gate is applied to.
            Default to None.
        static (bool, optional): Whether use static mode computation.
            Default to False.
        parent_graph (tq.QuantumGraph, optional): Parent QuantumGraph of
            current operation. Default to None.
        inverse (bool, optional): Whether inverse the gate. Default to False.
        comp_method (bool, optional): Use 'bmm' or 'einsum' method to perform
        matrix vector multiplication. Default to 'bmm'.

    Returns:
        None.

    """

    name = "cs"
    mat = mat_dict[name]
    gate_wrapper(
        name=name,
        mat=mat,
        method=comp_method,
        q_device=q_device,
        wires=wires,
        params=params,
        n_wires=n_wires,
        static=static,
        parent_graph=parent_graph,
        inverse=inverse,
    )


def csdg(
    q_device,
    wires,
    params=None,
    n_wires=None,
    static=False,
    parent_graph=None,
    inverse=False,
    comp_method="bmm",
):
    """Perform the csdg gate.
    Args:
        q_device (tq.QuantumDevice): The QuantumDevice.
        wires (Union[List[int], int]): Which qubit(s) to apply the gate.
        params (torch.Tensor, optional): Parameters (if any) of the gate.
            Default to None.
        n_wires (int, optional): Number of qubits the gate is applied to.
            Default to None.
        static (bool, optional): Whether use static mode computation.
            Default to False.
        parent_graph (tq.QuantumGraph, optional): Parent QuantumGraph of
            current operation. Default to None.
        inverse (bool, optional): Whether inverse the gate. Default to False.
        comp_method (bool, optional): Use 'bmm' or 'einsum' method to perform
        matrix vector multiplication. Default to 'bmm'.


    Returns:
        None.

    """
    name = "csdg"

    mat = mat_dict[name]
    gate_wrapper(
        name=name,
        mat=mat,
        method=comp_method,
        q_device=q_device,
        wires=wires,
        params=params,
        n_wires=n_wires,
        static=static,
        parent_graph=parent_graph,
        inverse=inverse,
    )


def csx(
    q_device,
    wires,
    params=None,
    n_wires=None,
    static=False,
    parent_graph=None,
    inverse=False,
    comp_method="bmm",
):
    """Perform the csx gate.

    Args:
        q_device (tq.QuantumDevice): The QuantumDevice.
        wires (Union[List[int], int]): Which qubit(s) to apply the gate.
        params (torch.Tensor, optional): Parameters (if any) of the gate.
            Default to None.
        n_wires (int, optional): Number of qubits the gate is applied to.
            Default to None.
        static (bool, optional): Whether use static mode computation.
            Default to False.
        parent_graph (tq.QuantumGraph, optional): Parent QuantumGraph of
            current operation. Default to None.
        inverse (bool, optional): Whether inverse the gate. Default to False.
        comp_method (bool, optional): Use 'bmm' or 'einsum' method to perform
        matrix vector multiplication. Default to 'bmm'.

    Returns:
        None.

    """
    name = "csx"
    mat = mat_dict[name]
    gate_wrapper(
        name=name,
        mat=mat,
        method=comp_method,
        q_device=q_device,
        wires=wires,
        params=params,
        n_wires=n_wires,
        static=static,
        parent_graph=parent_graph,
        inverse=inverse,
    )


def dcx(
    q_device,
    wires,
    params=None,
    n_wires=None,
    static=False,
    parent_graph=None,
    inverse=False,
    comp_method="bmm",
):
    """Perform the dcx gate.

    Args:
        q_device (tq.QuantumDevice): The QuantumDevice.
        wires (Union[List[int], int]): Which qubit(s) to apply the gate.
        params (torch.Tensor, optional): Parameters (if any) of the gate.
            Default to None.
        n_wires (int, optional): Number of qubits the gate is applied to.
            Default to None.
        static (bool, optional): Whether use static mode computation.
            Default to False.
        parent_graph (tq.QuantumGraph, optional): Parent QuantumGraph of
            current operation. Default to None.
        inverse (bool, optional): Whether inverse the gate. Default to False.
        comp_method (bool, optional): Use 'bmm' or 'einsum' method to perform
        matrix vector multiplication. Default to 'bmm'.

    Returns:
        None.

    """
    name = "dcx"
    mat = mat_dict[name]
    gate_wrapper(
        name=name,
        mat=mat,
        method=comp_method,
        q_device=q_device,
        wires=wires,
        params=params,
        n_wires=n_wires,
        static=static,
        parent_graph=parent_graph,
        inverse=inverse,
    )


def r(
    q_device,
    wires,
    params=None,
    n_wires=None,
    static=False,
    parent_graph=None,
    inverse=False,
    comp_method="bmm",
):
    """Perform the R gate.

    Args:
        q_device (tq.QuantumDevice): The QuantumDevice.
        wires (Union[List[int], int]): Which qubit(s) to apply the gate.
        params (torch.Tensor, optional): Parameters (if any) of the gate.
            Default to None.
        n_wires (int, optional): Number of qubits the gate is applied to.
            Default to None.
        static (bool, optional): Whether use static mode computation.
            Default to False.
        parent_graph (tq.QuantumGraph, optional): Parent QuantumGraph of
            current operation. Default to None.
        inverse (bool, optional): Whether inverse the gate. Default to False.
        comp_method (bool, optional): Use 'bmm' or 'einsum' method to perform
        matrix vector multiplication. Default to 'bmm'.

    Returns:
        None.

    """
    name = "r"
    mat = mat_dict[name]
    gate_wrapper(
        name=name,
        mat=mat,
        method=comp_method,
        q_device=q_device,
        wires=wires,
        params=params,
        n_wires=n_wires,
        static=static,
        parent_graph=parent_graph,
        inverse=inverse,
    )


def c4x(
    q_device,
    wires,
    params=None,
    n_wires=None,
    static=False,
    parent_graph=None,
    inverse=False,
    comp_method="bmm",
):
    """Perform the c4x gate.
    Args:
        q_device (tq.QuantumDevice): The QuantumDevice.
        wires (Union[List[int], int]): Which qubit(s) to apply the gate.
        params (torch.Tensor, optional): Parameters (if any) of the gate.
            Default to None.
        n_wires (int, optional): Number of qubits the gate is applied to.
            Default to None.
        static (bool, optional): Whether use static mode computation.
            Default to False.
        parent_graph (tq.QuantumGraph, optional): Parent QuantumGraph of
            current operation. Default to None.
        inverse (bool, optional): Whether inverse the gate. Default to False.
        comp_method (bool, optional): Use 'bmm' or 'einsum' method to perform
        matrix vector multiplication. Default to 'bmm'.
    Returns:
        None.
    """
    name = "c4x"
    mat = mat_dict[name]
    gate_wrapper(
        name=name,
        mat=mat,
        method=comp_method,
        q_device=q_device,
        wires=wires,
        params=params,
        n_wires=n_wires,
        static=static,
        parent_graph=parent_graph,
        inverse=inverse,
    )


def rc3x(
    q_device,
    wires,
    params=None,
    n_wires=None,
    static=False,
    parent_graph=None,
    inverse=False,
    comp_method="bmm",
):
    """Perform the rc3x (simplified 3-controlled Toffoli) gate.
    Args:
        q_device (tq.QuantumDevice): The QuantumDevice.
        wires (Union[List[int], int]): Which qubit(s) to apply the gate.
        params (torch.Tensor, optional): Parameters (if any) of the gate.
            Default to None.
        n_wires (int, optional): Number of qubits the gate is applied to.
            Default to None.
        static (bool, optional): Whether use static mode computation.
            Default to False.
        parent_graph (tq.QuantumGraph, optional): Parent QuantumGraph of
            current operation. Default to None.
        inverse (bool, optional): Whether inverse the gate. Default to False.
        comp_method (bool, optional): Use 'bmm' or 'einsum' method to perform
        matrix vector multiplication. Default to 'bmm'.
    Returns:
        None.
    """
    name = "rc3x"
    mat = mat_dict[name]
    gate_wrapper(
        name=name,
        mat=mat,
        method=comp_method,
        q_device=q_device,
        wires=wires,
        params=params,
        n_wires=n_wires,
        static=static,
        parent_graph=parent_graph,
        inverse=inverse,
    )


def rccx(
    q_device,
    wires,
    params=None,
    n_wires=None,
    static=False,
    parent_graph=None,
    inverse=False,
    comp_method="bmm",
):
    """Perform the rccx (simplified Toffoli) gate.
    Args:
        q_device (tq.QuantumDevice): The QuantumDevice.
        wires (Union[List[int], int]): Which qubit(s) to apply the gate.
        params (torch.Tensor, optional): Parameters (if any) of the gate.
            Default to None.
        n_wires (int, optional): Number of qubits the gate is applied to.
            Default to None.
        static (bool, optional): Whether use static mode computation.
            Default to False.
        parent_graph (tq.QuantumGraph, optional): Parent QuantumGraph of
            current operation. Default to None.
        inverse (bool, optional): Whether inverse the gate. Default to False.
        comp_method (bool, optional): Use 'bmm' or 'einsum' method to perform
        matrix vector multiplication. Default to 'bmm'.
    Returns:
        None.
    """
    name = "rccx"
    mat = mat_dict[name]
    gate_wrapper(
        name=name,
        mat=mat,
        method=comp_method,
        q_device=q_device,
        wires=wires,
        params=params,
        n_wires=n_wires,
        static=static,
        parent_graph=parent_graph,
        inverse=inverse,
    )


def globalphase(
    q_device,
    wires,
    params=None,
    n_wires=None,
    static=False,
    parent_graph=None,
    inverse=False,
    comp_method="bmm",
):
    """Perform the echoed cross-resonance gate.
    https://qiskit.org/documentation/stubs/qiskit.circuit.library.ECRGate.html
    Args:
        q_device (tq.QuantumDevice): The QuantumDevice.
        wires (Union[List[int], int]): Which qubit(s) to apply the gate.
        params (torch.Tensor, optional): Parameters (if any) of the gate.
            Default to None.
        n_wires (int, optional): Number of qubits the gate is applied to.
            Default to None.
        static (bool, optional): Whether use static mode computation.
            Default to False.
        parent_graph (tq.QuantumGraph, optional): Parent QuantumGraph of
            current operation. Default to None.
        inverse (bool, optional): Whether inverse the gate. Default to False.
        comp_method (bool, optional): Use 'bmm' or 'einsum' method to perform
        matrix vector multiplication. Default to 'bmm'.
    Returns:
        None.
    """
    name = "globalphase"
    mat = mat_dict[name]
    gate_wrapper(
        name=name,
        mat=mat,
        method=comp_method,
        q_device=q_device,
        wires=wires,
        params=params,
        n_wires=n_wires,
        static=static,
        parent_graph=parent_graph,
        inverse=inverse,
    )


def c3sx(
    q_device,
    wires,
    params=None,
    n_wires=None,
    static=False,
    parent_graph=None,
    inverse=False,
    comp_method="bmm",
):
    """Perform the c3sx gate.
    Args:
        q_device (tq.QuantumDevice): The QuantumDevice.
        wires (Union[List[int], int]): Which qubit(s) to apply the gate.
        params (torch.Tensor, optional): Parameters (if any) of the gate.
            Default to None.
        n_wires (int, optional): Number of qubits the gate is applied to.
            Default to None.
        static (bool, optional): Whether use static mode computation.
            Default to False.
        parent_graph (tq.QuantumGraph, optional): Parent QuantumGraph of
            current operation. Default to None.
        inverse (bool, optional): Whether inverse the gate. Default to False.
        comp_method (bool, optional): Use 'bmm' or 'einsum' method to perform
        matrix vector multiplication. Default to 'bmm'.
    Returns:
        None.
    """
    name = "c3sx"
    mat = mat_dict[name]
    gate_wrapper(
        name=name,
        mat=mat,
        method=comp_method,
        q_device=q_device,
        wires=wires,
        params=params,
        n_wires=n_wires,
        static=static,
        parent_graph=parent_graph,
        inverse=inverse,
    )


h = hadamard
sh = shadamard
x = paulix
y = pauliy
z = pauliz
xx = rxx
yy = ryy
zz = rzz
zx = rzx
cx = cnot
ccnot = toffoli
ccx = toffoli
u = u3
p = phaseshift
cp = cu1
cr = cu1
cphase = cu1
echoedcrossresonance = ecr
ch = chadamard


func_name_dict = {
    "hadamard": hadamard,
    "h": h,
    "sh": shadamard,
    "paulix": paulix,
    "pauliy": pauliy,
    "pauliz": pauliz,
    "i": i,
    "s": s,
    "t": t,
    "sx": sx,
    "cnot": cnot,
    "cz": cz,
    "cy": cy,
    "rx": rx,
    "ry": ry,
    "rz": rz,
    "rxx": rxx,
    "xx": xx,
    "ryy": ryy,
    "yy": yy,
    "rzz": rzz,
    "zz": zz,
    "rzx": rzx,
    "zx": zx,
    "swap": swap,
    "sswap": sswap,
    "cswap": cswap,
    "toffoli": toffoli,
    "phaseshift": phaseshift,
    "p": p,
    "cp": cp,
    "rot": rot,
    "multirz": multirz,
    "crx": crx,
    "cry": cry,
    "crz": crz,
    "crot": crot,
    "u1": u1,
    "u2": u2,
    "u3": u3,
    "u": u,
    "cu1": cu1,
    "cphase": cphase,
    "cr": cr,
    "cu2": cu2,
    "cu3": cu3,
    "cu": cu,
    "kron":kron,
    "su4": su4,
    "qubitunitary": qubitunitary,
    "qubitunitaryfast": qubitunitaryfast,
    "qubitunitarystrict": qubitunitarystrict,
    "multicnot": multicnot,
    "multixcnot": multixcnot,
    "x": x,
    "y": y,
    "z": z,
    "cx": cx,
    "ccnot": ccnot,
    "ccx": ccx,
    "reset": reset,
    "singleexcitation": singleexcitation,
    "ecr": ecr,
    "echoedcrossresonance": echoedcrossresonance,
    "qft": qft,
    "sdg": sdg,
    "tdg": tdg,
    "sxdg": sxdg,
    "ch": ch,
    "ccz": ccz,
    "iswap": iswap,
    "cs": cs,
    "csdg": csdg,
    "csx": csx,
    "chadamard": chadamard,
    "ccz": ccz,
    "dcx": dcx,
    "xxminyy": xxminyy,
    "xxplusyy": xxplusyy,
    "c3x": c3x,
    "r": r,
    "globalphase": globalphase,
    "c3sx": c3sx,
    "rccx": rccx,
    "rc3x": rc3x,
    "c4x": c4x,
}
